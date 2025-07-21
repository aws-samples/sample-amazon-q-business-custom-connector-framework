import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterator, List

import boto3
import gitlab
from gitlab.v4.objects import Project, ProjectIssue, ProjectMergeRequest
from pydantic import BaseModel, Field

from custom_connector_framework.ccf_client import CCFClient
from custom_connector_framework.custom_connector_interface import \
    QBusinessCustomConnectorInterface
from custom_connector_framework.models.document import (Document, DocumentFile,
                                                        DocumentMetadata)
from custom_connector_framework.models.qbusiness import (AccessControl,
                                                         AccessType,
                                                         MemberRelation,
                                                         MembershipType,
                                                         Principal,
                                                         PrincipalUser)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Environment variable names
ENV_CONFIG_FILE = "GITLAB_CONFIG_PATH"
ENV_APP_ID = "Q_BUSINESS_APP_ID"
ENV_INDEX_ID = "Q_BUSINESS_INDEX_ID"
ENV_DATA_SOURCE_ID = "Q_BUSINESS_DATA_SOURCE_ID"
ENV_S3_BUCKET = "OUTPUT_BUCKET"  # Optional, but needed for files larger than 10MB
ENV_REGION = "AWS_REGION"  # Provided by framework
ENV_CCF_ENDPOINT = "CUSTOM_CONNECTOR_FRAMEWORK_API_ENDPOINT"
ENV_CCF_CONNECTOR_ID = "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID"
ENV_LOG_LEVEL = "LOG_LEVEL"
ENV_GITLAB_TOKEN = "GITLAB_TOKEN"  # Direct token from environment variable
ENV_GITLAB_TOKEN_SECRET_ARN = "GITLAB_TOKEN_SECRET_ARN"  # ARN of the secret in Secrets Manager
ENV_GITLAB_URL = "GITLAB_URL"


class MissingEmailPolicy(str, Enum):
    """Policy for handling missing emails in ACLs"""

    OPEN = "open"  # Allow access when email is missing (fail open)
    CLOSED = "closed"  # Deny access when email is missing (fail closed)


class GitLabConfig(BaseModel):
    """Configuration for GitLab connector"""

    gl_repositories_to_exclude: List[str] = Field(default_factory=list)
    gl_file_extensions: List[str] = Field(
        default_factory=lambda: [
            ".py",
            ".js",
            ".java",
            ".ts",
            ".go",
            ".rb",
            ".md",
            ".json",
            ".yml",
            ".yaml",
            ".xml",
            ".html",
            ".css",
            ".sh",
            ".bash",
            ".txt",
            ".sql",
            ".c",
            ".cpp",
            ".h",
            ".cs",
            ".php",
            ".scala",
            ".kt",
            ".rs",
        ]
    )
    gl_excluded_paths: List[str] = Field(
        default_factory=lambda: [
            "node_modules",
            ".git",
            "__pycache__",
            "venv",
            ".venv",
            "dist",
            "build",
            ".idea",
            ".vscode",
            "coverage",
            "target",
        ]
    )
    gl_include_issues: bool = True
    gl_include_merge_requests: bool = True
    gl_include_wiki: bool = True
    gl_include_project_members: bool = True
    gl_acl_missing_email_policy: MissingEmailPolicy = MissingEmailPolicy.CLOSED  # Policy for handling missing emails
    gl_max_projects: int = 100  # Limit number of projects to process
    gl_default_branch_only: bool = True  # Only process default branch


class GitLabConnector(QBusinessCustomConnectorInterface):
    def __init__(self, config: GitLabConfig, gitlab_token: str, gitlab_url: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config

        # Initialize GitLab client
        self.gl = gitlab.Gitlab(url=gitlab_url, private_token=gitlab_token)
        self.gl.auth()

        # Track documents to delete
        self.documents_to_delete = []

    def _create_access_control_from_members(self, project: Project) -> List[AccessControl]:
        """Create AccessControl objects from project members"""
        if not self.config.gl_include_project_members:
            return []

        try:
            access_controls = []
            members = project.users.list(get_all=True)

            # Track members with and without emails
            members_with_email = 0
            members_without_email = 0

            # Group members by access level
            principals_by_access = {}
            for member in members:
                if not hasattr(member, "public_email") or not member.public_email:
                    members_without_email += 1
                    continue  # Skip members without email

                members_with_email += 1

                # Map GitLab access levels to Q Business access types
                # 10: Guest, 20: Reporter, 30: Developer, 40: Maintainer, 50: Owner
                access_type = AccessType.ALLOW

                if access_type not in principals_by_access:
                    principals_by_access[access_type] = []

                principals_by_access[access_type].append(
                    Principal(
                        user=PrincipalUser(
                            id=member.email,
                            access=access_type,
                            membershipType=MembershipType.INDEX,
                        )
                    )
                )

            # Log statistics about members with/without emails
            logger.info(
                f"Project {project.name}: {members_with_email} members with email, "
                f"{members_without_email} members without email"
            )

            # If no members have emails, apply the missing email policy
            if members_with_email == 0:
                if self.config.gl_acl_missing_email_policy == MissingEmailPolicy.OPEN:
                    logger.info(
                        f"Project {project.name}: No members with email found, "
                        f"using OPEN policy (allowing access to all)"
                    )
                    return []  # Empty ACL list allows access to all
                else:  # CLOSED policy
                    logger.info(
                        f"Project {project.name}: No members with email found, using CLOSED policy (restricting access)"
                    )
                    # Create a restrictive ACL that denies access to everyone
                    # Use a non-existent email to ensure no one matches
                    return [
                        AccessControl(
                            memberRelation=MemberRelation.OR,
                            principals=[
                                Principal(
                                    user=PrincipalUser(
                                        id="no-access@restricted-document.invalid",
                                        access=AccessType.ALLOW,
                                        membershipType=MembershipType.INDEX,
                                    )
                                )
                            ],
                        )
                    ]

            # Create access control for each access type
            for access_type, principals in principals_by_access.items():
                if principals:
                    access_controls.append(
                        AccessControl(
                            memberRelation=MemberRelation.OR,
                            principals=principals,
                        )
                    )

            return access_controls
        except Exception as e:
            logger.warning(f"Failed to get members for project {project.name}: {e}")
            # If exception occurs, apply the missing email policy
            if self.config.gl_acl_missing_email_policy == MissingEmailPolicy.OPEN:
                logger.info(f"Project {project.name}: Exception occurred while getting members, using OPEN policy")
                return []  # Empty ACL list allows access to all
            else:  # CLOSED policy
                logger.info(f"Project {project.name}: Exception occurred while getting members, using CLOSED policy")
                # Create a restrictive ACL that denies access to everyone
                return [
                    AccessControl(
                        memberRelation=MemberRelation.OR,
                        principals=[
                            Principal(
                                user=PrincipalUser(
                                    id="no-access@restricted-document.invalid",
                                    access=AccessType.ALLOW,
                                    membershipType=MembershipType.INDEX,
                                )
                            )
                        ],
                    )
                ]

    def _convert_code_to_markdown(self, file_path: str, content: str, project_url: str, file_url: str) -> str:
        """Convert source code to markdown format with syntax highlighting"""
        file_extension = os.path.splitext(file_path)[1][1:]  # Remove the dot
        language = file_extension if file_extension else "text"

        markdown_content = f"# File: {file_path}\n"
        markdown_content += f"[View on GitLab]({file_url})\n\n"
        markdown_content += f"Project: {project_url}\n\n"
        markdown_content += f"Last Updated: {datetime.now(timezone.utc).isoformat()}\n\n"
        markdown_content += f"```{language}\n{content}\n```\n"

        return markdown_content

    def _convert_issue_to_markdown(self, issue: ProjectIssue, project_url: str) -> str:
        """Convert GitLab issue to markdown format"""
        markdown_content = f"# Issue #{issue.iid}: {issue.title}\n\n"
        markdown_content += f"[View on GitLab]({issue.web_url})\n\n"
        markdown_content += f"Project: {project_url}\n\n"
        markdown_content += f"**Status:** {issue.state}\n"
        markdown_content += f"**Created:** {issue.created_at}\n"
        markdown_content += f"**Updated:** {issue.updated_at}\n"

        if hasattr(issue, "author") and issue.author:
            markdown_content += f"**Author:** {issue.author['name']}\n"

        if hasattr(issue, "assignees") and issue.assignees:
            assignee_names = [assignee["name"] for assignee in issue.assignees]
            markdown_content += f"**Assignees:** {', '.join(assignee_names)}\n"

        if hasattr(issue, "labels") and issue.labels:
            markdown_content += f"**Labels:** {', '.join(issue.labels)}\n"

        markdown_content += "\n## Description\n\n"
        markdown_content += issue.description if issue.description else "*No description provided*"

        # Add notes/comments if available
        try:
            notes = issue.notes.list(all=True)
            if notes:
                markdown_content += "\n\n## Comments\n\n"
                for note in notes:
                    if not note.system:  # Skip system notes
                        author_name = note.author["name"] if hasattr(note, "author") else "Unknown"
                        markdown_content += f"### {author_name} commented on {note.created_at}\n\n"
                        markdown_content += f"{note.body}\n\n"
                        markdown_content += "---\n\n"
        except Exception as e:
            logger.warning(f"Failed to fetch comments for issue #{issue.iid}: {e}")

        return markdown_content

    def _convert_mr_to_markdown(self, mr: ProjectMergeRequest, project_url: str) -> str:
        """Convert GitLab merge request to markdown format"""
        markdown_content = f"# Merge Request #{mr.iid}: {mr.title}\n\n"
        markdown_content += f"[View on GitLab]({mr.web_url})\n\n"
        markdown_content += f"Project: {project_url}\n\n"
        markdown_content += f"**Status:** {mr.state}\n"
        markdown_content += f"**Created:** {mr.created_at}\n"
        markdown_content += f"**Updated:** {mr.updated_at}\n"

        if hasattr(mr, "author") and mr.author:
            markdown_content += f"**Author:** {mr.author['name']}\n"

        if hasattr(mr, "assignees") and mr.assignees:
            assignee_names = [assignee["name"] for assignee in mr.assignees]
            markdown_content += f"**Assignees:** {', '.join(assignee_names)}\n"

        if hasattr(mr, "labels") and mr.labels:
            markdown_content += f"**Labels:** {', '.join(mr.labels)}\n"

        markdown_content += f"**Source Branch:** {mr.source_branch}\n"
        markdown_content += f"**Target Branch:** {mr.target_branch}\n"

        markdown_content += "\n## Description\n\n"
        markdown_content += mr.description if mr.description else "*No description provided*"

        # Add notes/comments if available
        try:
            notes = mr.notes.list(all=True)
            if notes:
                markdown_content += "\n\n## Comments\n\n"
                for note in notes:
                    if not note.system:  # Skip system notes
                        author_name = note.author["name"] if hasattr(note, "author") else "Unknown"
                        markdown_content += f"### {author_name} commented on {note.created_at}\n\n"
                        markdown_content += f"{note.body}\n\n"
                        markdown_content += "---\n\n"
        except Exception as e:
            logger.warning(f"Failed to fetch comments for MR #{mr.iid}: {e}")

        return markdown_content

    def _convert_wiki_to_markdown(self, wiki_content: str, title: str, project_url: str, wiki_url: str) -> str:
        """Convert GitLab wiki to markdown format"""
        markdown_content = f"# Wiki: {title}\n\n"
        markdown_content += f"[View on GitLab]({wiki_url})\n\n"
        markdown_content += f"Project: {project_url}\n\n"
        markdown_content += f"Last Updated: {datetime.now(timezone.utc).isoformat()}\n\n"
        markdown_content += "## Content\n\n"
        markdown_content += wiki_content

        return markdown_content

    def _generate_project_summary(self, project: Project) -> str:
        """Generate a markdown summary of the project"""
        markdown_content = f"# Project: {project.name}\n\n"
        markdown_content += f"[View on GitLab]({project.web_url})\n\n"

        markdown_content += f"**ID:** {project.id}\n"
        markdown_content += f"**Path:** {project.path_with_namespace}\n"
        markdown_content += f"**Visibility:** {project.visibility}\n"
        markdown_content += f"**Created:** {project.created_at}\n"
        markdown_content += f"**Last Activity:** {project.last_activity_at}\n\n"

        if project.description:
            markdown_content += "## Description\n\n"
            markdown_content += f"{project.description}\n\n"

        # Add README if available
        try:
            readme = project.files.get(file_path="README.md", ref=project.default_branch)
            if readme:
                markdown_content += "## README\n\n"
                markdown_content += readme.decode().decode("utf-8")
        except Exception:
            # README might not exist or be named differently
            pass

        return markdown_content

    def _create_temp_markdown_file(self, content: str) -> Path:
        """Create a temporary markdown file with the given content"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as temp_file:
            temp_file.write(content)
            temp_file.flush()
            temp_file_path = Path(temp_file.name)
        return temp_file_path

    def _process_project_files(self, project: Project) -> Iterator[Document]:
        """Process files in a GitLab project"""
        try:
            default_branch = project.default_branch
            file_extensions = self.config.gl_file_extensions
            excluded_paths = self.config.gl_excluded_paths

            # Get repository tree recursively
            items = project.repository_tree(recursive=True, ref=default_branch, all=True)
            logger.info(f"Found {len(items)} items in repository tree for project {project.name}")

            processed_files = 0
            skipped_files = 0

            for item in items:
                if item["type"] != "blob":  # Skip directories
                    continue

                file_path = item["path"]

                # Skip excluded paths
                if any(excluded in file_path for excluded in excluded_paths):
                    skipped_files += 1
                    continue

                # Check if file extension is in the allowed list
                if not any(file_path.endswith(ext) for ext in file_extensions):
                    skipped_files += 1
                    continue

                try:
                    # Get file content
                    file_content = project.files.get(file_path=file_path, ref=default_branch)
                    content = file_content.decode().decode("utf-8")

                    # Convert to markdown
                    file_url = f"{project.web_url}/-/blob/{default_branch}/{file_path}"
                    markdown_content = self._convert_code_to_markdown(file_path, content, project.web_url, file_url)

                    # Create temporary file
                    temp_file_path = self._create_temp_markdown_file(markdown_content)

                    # Create document ID
                    doc_id = f"gl_{project.id}_file_{hashlib.sha256(file_path.encode()).hexdigest()}"

                    # Get access controls from project members
                    access_control_list = self._create_access_control_from_members(project)

                    # Create document
                    doc = Document(
                        id=doc_id,
                        file=DocumentFile(temp_file_path),
                        metadata=DocumentMetadata(
                            title=f"{project.name} - {file_path}",
                            source_uri=file_url,
                            attributes={
                                "gl_project_id": str(project.id),
                                "gl_project_name": project.name,
                                "gl_file_path": file_path,
                                "gl_content_type": "source_code",
                                "gl_repository": project.path_with_namespace,
                            },
                            access_control_list=access_control_list,
                        ),
                    )
                    processed_files += 1
                    yield doc

                except Exception as e:
                    logger.warning(f"Failed to process file {file_path} in project {project.name}: {e}")
                    skipped_files += 1

            logger.info(
                f"Project {project.name} file processing summary: {processed_files} files processed, "
                f"{skipped_files} files skipped"
            )

        except Exception as e:
            logger.error(f"Failed to process files for project {project.name}: {e}")

    def _process_project_issues(self, project: Project) -> Iterator[Document]:
        """Process issues in a GitLab project"""
        try:
            # Check if issues should be processed
            if not self.config.gl_include_issues:
                return

            # Get issues
            issues = project.issues.list(all=True, state="all")
            logger.info(f"Found {len(issues)} issues in project {project.name}")

            processed_issues = 0
            skipped_issues = 0

            for issue in issues:
                try:
                    # Convert to markdown
                    markdown_content = self._convert_issue_to_markdown(issue, project.web_url)

                    # Create temporary file
                    temp_file_path = self._create_temp_markdown_file(markdown_content)

                    # Create document ID
                    doc_id = f"gl_{project.id}_issue_{issue.iid}"

                    # Get access controls from project members
                    access_control_list = self._create_access_control_from_members(project)

                    # Create document
                    doc = Document(
                        id=doc_id,
                        file=DocumentFile(temp_file_path),
                        metadata=DocumentMetadata(
                            title=f"{project.name} - Issue #{issue.iid}: {issue.title}",
                            source_uri=issue.web_url,
                            attributes={
                                "gl_project_id": str(project.id),
                                "gl_project_name": project.name,
                                "gl_issue_id": str(issue.iid),
                                "gl_issue_state": issue.state,
                                "gl_content_type": "issue",
                                "gl_repository": project.path_with_namespace,
                            },
                            access_control_list=access_control_list,
                        ),
                    )
                    processed_issues += 1
                    yield doc

                except Exception as e:
                    logger.warning(f"Failed to process issue #{issue.iid} in project {project.name}: {e}")
                    skipped_issues += 1

            logger.info(
                f"Project {project.name} issue processing summary: {processed_issues} issues processed, "
                f"{skipped_issues} issues skipped"
            )

        except Exception as e:
            logger.error(f"Failed to process issues for project {project.name}: {e}")

    def _process_project_merge_requests(self, project: Project) -> Iterator[Document]:
        """Process merge requests in a GitLab project"""
        try:
            # Check if merge requests should be processed
            if not self.config.gl_include_merge_requests:
                return

            # Get merge requests
            mrs = project.mergerequests.list(all=True, state="all")
            logger.info(f"Found {len(mrs)} merge requests in project {project.name}")

            processed_mrs = 0
            skipped_mrs = 0

            for mr in mrs:
                try:
                    # Convert to markdown
                    markdown_content = self._convert_mr_to_markdown(mr, project.web_url)

                    # Create temporary file
                    temp_file_path = self._create_temp_markdown_file(markdown_content)

                    # Create document ID
                    doc_id = f"gl_{project.id}_mr_{mr.iid}"

                    # Get access controls from project members
                    access_control_list = self._create_access_control_from_members(project)

                    # Create document
                    doc = Document(
                        id=doc_id,
                        file=DocumentFile(temp_file_path),
                        metadata=DocumentMetadata(
                            title=f"{project.name} - MR #{mr.iid}: {mr.title}",
                            source_uri=mr.web_url,
                            attributes={
                                "gl_project_id": str(project.id),
                                "gl_project_name": project.name,
                                "gl_mr_id": str(mr.iid),
                                "gl_mr_state": mr.state,
                                "gl_content_type": "merge_request",
                                "gl_repository": project.path_with_namespace,
                            },
                            access_control_list=access_control_list,
                        ),
                    )
                    processed_mrs += 1
                    yield doc

                except Exception as e:
                    logger.warning(f"Failed to process merge request #{mr.iid} in project {project.name}: {e}")
                    skipped_mrs += 1

            logger.info(
                f"Project {project.name} merge request processing summary: {processed_mrs} MRs processed, "
                f"{skipped_mrs} MRs skipped"
            )

        except Exception as e:
            logger.error(f"Failed to process merge requests for project {project.name}: {e}")

    def _process_project_wiki(self, project: Project) -> Iterator[Document]:
        """Process wiki pages in a GitLab project"""
        try:
            # Check if wiki should be processed
            if not self.config.gl_include_wiki:
                return

            # Check if project has wiki enabled
            if not project.wiki_enabled:
                return

            try:
                # Get wiki pages list
                wiki_pages = project.wikis.list(all=True)
                logger.info(f"Found {len(wiki_pages)} wiki pages in project {project.name}")

                for page in wiki_pages:
                    try:
                        # Get the full wiki page object to access content
                        # This is necessary because the list() method only returns partial objects
                        full_page = project.wikis.get(page.slug)

                        if not hasattr(full_page, "content") or not full_page.content:
                            logger.warning(f"Wiki page {page.slug} has no content, skipping")
                            continue

                        # Convert to markdown
                        wiki_url = f"{project.web_url}/-/wikis/{page.slug}"
                        markdown_content = self._convert_wiki_to_markdown(
                            full_page.content, page.title, project.web_url, wiki_url
                        )

                        # Create temporary file
                        temp_file_path = self._create_temp_markdown_file(markdown_content)

                        # Create document ID
                        doc_id = f"gl_{project.id}_wiki_{page.slug}"

                        # Get access controls from project members
                        access_control_list = self._create_access_control_from_members(project)

                        # Create document
                        doc = Document(
                            id=doc_id,
                            file=DocumentFile(temp_file_path),
                            metadata=DocumentMetadata(
                                title=f"{project.name} - Wiki: {page.title}",
                                source_uri=wiki_url,
                                attributes={
                                    "gl_project_id": str(project.id),
                                    "gl_project_name": project.name,
                                    "gl_wiki_slug": page.slug,
                                    "gl_content_type": "wiki",
                                    "gl_repository": project.path_with_namespace,
                                },
                                access_control_list=access_control_list,
                            ),
                        )
                        logger.info(f"Processed wiki page: {page.title} in project {project.name}")
                        yield doc

                    except Exception as e:
                        logger.warning(f"Failed to process wiki page {page.slug} in project {project.name}: {e}")

            except Exception as e:
                logger.warning(f"Failed to access wiki for project {project.name}: {e}")

        except Exception as e:
            logger.error(f"Failed to process wiki for project {project.name}: {e}")

    def _process_project_summary(self, project: Project) -> Iterator[Document]:
        """Process project summary"""
        try:
            # Generate project summary
            markdown_content = self._generate_project_summary(project)

            # Create temporary file
            temp_file_path = self._create_temp_markdown_file(markdown_content)

            # Create document ID
            doc_id = f"gl_{project.id}_summary"

            # Get access controls from project members
            access_control_list = self._create_access_control_from_members(project)

            # Create document
            doc = Document(
                id=doc_id,
                file=DocumentFile(temp_file_path),
                metadata=DocumentMetadata(
                    title=f"{project.name} - Project Summary",
                    source_uri=project.web_url,
                    attributes={
                        "gl_project_id": str(project.id),
                        "gl_project_name": project.name,
                        "gl_content_type": "project_summary",
                        "gl_repository": project.path_with_namespace,
                    },
                    access_control_list=access_control_list,
                ),
            )
            yield doc

        except Exception as e:
            logger.error(f"Failed to process summary for project {project.name}: {e}")

    def get_documents_to_add(self) -> Iterator[Document]:
        """Get documents to add to Amazon Q Business"""
        # Initialize counters for resource types
        resource_counts = {
            "project_summary": 0,
            "source_code": 0,
            "issue": 0,
            "merge_request": 0,
            "wiki": 0,
            "total": 0,
        }

        # Get all projects the user has access to
        try:
            projects = self.gl.projects.list(all=True, min_access_level=20)  # Reporter level or higher
            logger.info(f"Found {len(projects)} projects")

            # Apply max projects limit
            projects = projects[: self.config.gl_max_projects]

            # Filter out excluded repositories
            excluded_repos = set(self.config.gl_repositories_to_exclude)
            projects = [p for p in projects if p.path_with_namespace not in excluded_repos]
            logger.info(f"Processing {len(projects)} projects after filtering")

            # Process each project
            for project in projects:
                try:
                    logger.info(f"Processing project: {project.name} (ID: {project.id})")

                    # Process project summary
                    for doc in self._process_project_summary(project):
                        resource_counts["project_summary"] += 1
                        resource_counts["total"] += 1
                        yield doc

                    # Process project files
                    file_count = 0
                    for doc in self._process_project_files(project):
                        file_count += 1
                        resource_counts["source_code"] += 1
                        resource_counts["total"] += 1
                        yield doc
                    logger.info(f"Processed {file_count} source code files in project {project.name}")

                    # Process project issues
                    issue_count = 0
                    for doc in self._process_project_issues(project):
                        issue_count += 1
                        resource_counts["issue"] += 1
                        resource_counts["total"] += 1
                        yield doc
                    logger.info(f"Processed {issue_count} issues in project {project.name}")

                    # Process project merge requests
                    mr_count = 0
                    for doc in self._process_project_merge_requests(project):
                        mr_count += 1
                        resource_counts["merge_request"] += 1
                        resource_counts["total"] += 1
                        yield doc
                    logger.info(f"Processed {mr_count} merge requests in project {project.name}")

                    # Process project wiki
                    wiki_count = 0
                    for doc in self._process_project_wiki(project):
                        wiki_count += 1
                        resource_counts["wiki"] += 1
                        resource_counts["total"] += 1
                        yield doc
                    logger.info(f"Processed {wiki_count} wiki pages in project {project.name}")

                    # Log summary for this project
                    logger.info(
                        f"Project {project.name} summary: {file_count} files, {issue_count} issues, "
                        f"{mr_count} merge requests, {wiki_count} wiki pages"
                    )

                except Exception as e:
                    logger.error(f"Failed to process project {project.name}: {e}")

            # Log overall summary
            logger.info("=== GitLab Connector Ingestion Summary ===")
            logger.info(f"Total documents: {resource_counts['total']}")
            logger.info(f"Project summaries: {resource_counts['project_summary']}")
            logger.info(f"Source code files: {resource_counts['source_code']}")
            logger.info(f"Issues: {resource_counts['issue']}")
            logger.info(f"Merge requests: {resource_counts['merge_request']}")
            logger.info(f"Wiki pages: {resource_counts['wiki']}")
            logger.info("======================================")

        except Exception as e:
            logger.error(f"Failed to list projects: {e}")

    def get_documents_to_delete(self) -> Iterator[str]:
        """Get document IDs to delete from Amazon Q Business"""
        return iter(self.documents_to_delete)


def load_config_file(file_path: str) -> GitLabConfig:
    """Load and validate the configuration file"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # Convert to GitLabConfig
        return GitLabConfig(**config_data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")
    except Exception as e:
        raise ValueError(f"Error loading configuration file: {e}")


def get_gitlab_token(token_env: str, secret_arn_env: str, region: str) -> str:
    """
    Get GitLab token from environment variable or Secrets Manager.

    Args:
        token_env: Environment variable name for direct token
        secret_arn_env: Environment variable name for secret ARN
        region: AWS region

    Returns:
        GitLab token string
    """
    # First try to get token directly from environment variable
    token = os.getenv(token_env)
    if token:
        logger.info("Using GitLab token from environment variable")
        return token

    # If not found, try to get from Secrets Manager
    secret_arn = os.getenv(secret_arn_env)
    if secret_arn:
        try:
            logger.info("Retrieving GitLab token from Secrets Manager")
            secrets_client = boto3.client("secretsmanager", region_name=region)
            response = secrets_client.get_secret_value(SecretId=secret_arn)
            if "SecretString" in response:
                return response["SecretString"]
        except Exception as e:
            logger.error(f"Failed to retrieve GitLab token from Secrets Manager: {e}")

    return None


def get_config():
    """Get configuration from environment variables and command line arguments."""
    parser = argparse.ArgumentParser(description="GitLab Connector for Amazon Q Business")

    parser.add_argument(
        "--config-file",
        type=str,
        default=os.getenv(ENV_CONFIG_FILE, "/var/task/gitlab_config.json"),
        help="Path to the GitLab configuration JSON file",
    )
    parser.add_argument(
        "--app-id",
        type=str,
        default=os.getenv(ENV_APP_ID),
        help="Amazon Q Business Application ID",
    )
    parser.add_argument(
        "--index-id",
        type=str,
        default=os.getenv(ENV_INDEX_ID),
        help="Amazon Q Business Index ID",
    )
    parser.add_argument(
        "--data-source-id",
        type=str,
        default=os.getenv(ENV_DATA_SOURCE_ID),
        help="Amazon Q Business Data Source ID",
    )
    parser.add_argument(
        "--s3-bucket",
        type=str,
        default=os.getenv(ENV_S3_BUCKET),
        help="S3 bucket name for large document storage (optional)",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=os.getenv(ENV_REGION, "us-east-1"),
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=os.getenv(ENV_LOG_LEVEL, "INFO"),
        help="Set the logging level",
    )
    parser.add_argument(
        "--ccf-endpoint",
        type=str,
        default=os.getenv(ENV_CCF_ENDPOINT),
        help="The endpoint for the custom connector framework",
    )
    parser.add_argument(
        "--ccf-connector-id",
        type=str,
        default=os.getenv(ENV_CCF_CONNECTOR_ID),
        help="The custom connector ID for the custom connector framework",
    )
    parser.add_argument(
        "--gitlab-token",
        type=str,
        default=os.getenv(ENV_GITLAB_TOKEN),
        help="GitLab API token",
    )
    parser.add_argument(
        "--gitlab-token-secret-arn",
        type=str,
        default=os.getenv(ENV_GITLAB_TOKEN_SECRET_ARN),
        help="ARN of the secret in Secrets Manager containing the GitLab API token",
    )
    parser.add_argument(
        "--gitlab-url",
        type=str,
        default=os.getenv(ENV_GITLAB_URL, "https://gitlab.com"),
        help="GitLab instance URL",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in test mode (process documents but don't upload to Q Business)",
    )

    args = parser.parse_args()

    # Get GitLab token from environment or Secrets Manager
    gitlab_token = args.gitlab_token
    if not gitlab_token:
        gitlab_token = get_gitlab_token(ENV_GITLAB_TOKEN, ENV_GITLAB_TOKEN_SECRET_ARN, args.region)

    # Validate required parameters
    required_params = {
        "config_file": args.config_file,
        "app_id": args.app_id,
        "index_id": args.index_id,
        "data_source_id": args.data_source_id,
        "gitlab_token": gitlab_token,
    }

    missing_params = [k for k, v in required_params.items() if not v]
    if missing_params:
        parser.error(f"Missing required parameters: {', '.join(missing_params)}")

    return args


def main():
    """
    Main function that can be run either through CLI or with environment variables.

    Environment variables:
    GITLAB_CONFIG_PATH="/var/task/gitlab_config.json"
    Q_BUSINESS_APP_ID="your-app-id"
    Q_BUSINESS_INDEX_ID="your-index-id"
    Q_BUSINESS_DATA_SOURCE_ID="your-data-source-id"
    OUTPUT_BUCKET="your-bucket"
    AWS_REGION="your-region"
    CUSTOM_CONNECTOR_FRAMEWORK_API_ENDPOINT="your-ccf-endpoint"
    CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID="your-ccf-connector-id"
    GITLAB_TOKEN="your-gitlab-token"
    GITLAB_TOKEN_SECRET_ARN="arn:aws:secretsmanager:region:account:secret:name"
    GITLAB_URL="https://gitlab.com"
    LOG_LEVEL="INFO"

    The CCF client initialization requires two parameters:
    1. A boto3 client for the CCF service, created with the endpoint URL and region
    2. The connector ID for the custom connector

    When deployed by the Custom Connector Framework, these values are provided as environment variables:
    - CUSTOM_CONNECTOR_FRAMEWORK_API_ENDPOINT: The endpoint URL for the CCF API
    - CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID: The ID of the custom connector
    """
    start_time = datetime.now(timezone.utc)
    config = get_config()
    logging.getLogger().setLevel(getattr(logging, config.log_level))

    try:
        # Load and validate the configuration file
        gitlab_config = load_config_file(config.config_file)

        # Get GitLab token from environment or Secrets Manager if not already retrieved
        gitlab_token = config.gitlab_token
        if not gitlab_token:
            gitlab_token = get_gitlab_token(ENV_GITLAB_TOKEN, ENV_GITLAB_TOKEN_SECRET_ARN, config.region)
            if not gitlab_token:
                raise ValueError("GitLab token not found in environment or Secrets Manager")

        # Initialize clients
        q_client = boto3.client("qbusiness", region_name=config.region)
        s3_client = boto3.client("s3", region_name=config.region) if config.s3_bucket else None
        ccf_client = None

        if config.ccf_endpoint and config.ccf_connector_id:
            try:
                boto3_ccf_client = boto3.client(
                    "ccf",
                    endpoint_url=config.ccf_endpoint,
                    region_name=config.region,
                )
                # Initialize the CCFClient with the boto3 client and connector ID
                ccf_client = CCFClient(
                    ccf_client=boto3_ccf_client,
                    connector_id=config.ccf_connector_id,
                )
            except Exception as e:
                logger.error(f"Failed to initialize CCF client: {e}")
                logger.warning("Continuing without CCF client")

        logger.info("Initializing GitLab Connector...")
        connector = GitLabConnector(
            config=gitlab_config,
            gitlab_token=gitlab_token,  # Use the retrieved token
            gitlab_url=config.gitlab_url,
            ccf_client=ccf_client,
            qbusiness_client=q_client,
            qbusiness_app_id=config.app_id,
            qbusiness_index_id=config.index_id,
            qbusiness_data_source_id=config.data_source_id,
            s3_client=s3_client,
            s3_bucket=config.s3_bucket,
        )

        logger.info("Starting sync process...")

        if hasattr(config, "test_mode") and config.test_mode:
            logger.info("Running in test mode - documents will be processed but not uploaded to Q Business")
            # Just get the documents and log them
            docs_to_add = list(connector.get_documents_to_add())
            logger.info(f"Found {len(docs_to_add)} documents to add")
            for doc in docs_to_add[:10]:  # Show first 10 docs
                logger.info(f"Document: {doc.id} - {doc.metadata.title}")

            if len(docs_to_add) > 10:
                logger.info(f"... and {len(docs_to_add) - 10} more documents")

            docs_to_delete = list(connector.get_documents_to_delete())
            logger.info(f"Found {len(docs_to_delete)} documents to delete")
        else:
            # Normal sync process
            connector.sync()

        end_time = datetime.now(timezone.utc)
        duration = end_time - start_time
        logger.info("=== GitLab Connector Execution Summary ===")
        logger.info(f"Start time: {start_time.isoformat()}")
        logger.info(f"End time: {end_time.isoformat()}")
        logger.info(f"Total duration: {duration.total_seconds():.2f} seconds")
        logger.info(f"GitLab instance: {config.gitlab_url}")
        logger.info(f"Q Business App ID: {config.app_id}")
        logger.info(f"Q Business Index ID: {config.index_id}")
        logger.info(f"Q Business Data Source ID: {config.data_source_id}")
        logger.info("======================================")
        logger.info("Sync process completed successfully!")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
