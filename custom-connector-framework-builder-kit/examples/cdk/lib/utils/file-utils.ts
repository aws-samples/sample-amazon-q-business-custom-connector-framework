import * as fs from "fs";
import * as path from "path";

/**
 * Sanitizes a file path to prevent path traversal attacks
 * @param basePath The base directory that should contain the path
 * @param userPath The path to sanitize
 * @returns A safe path that is guaranteed to be within the base directory
 */
export function sanitizePath(basePath: string, userPath: string): string {
  // Normalize the paths to resolve any '..' or '.' segments
  const normalizedBase = path.normalize(basePath);
  const joinedPath = path.join(normalizedBase, userPath);
  const normalizedPath = path.normalize(joinedPath);

  // Ensure the normalized path starts with the normalized base path
  if (!normalizedPath.startsWith(normalizedBase)) {
    throw new Error(
      `Path traversal detected: ${userPath} attempts to access outside of ${basePath}`,
    );
  }

  return normalizedPath;
}

/**
 * Creates a directory if it doesn't exist
 * @param dirPath Path to the directory to create
 */
export function ensureDirectoryExists(dirPath: string): void {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

/**
 * Copies a directory recursively with exclusion patterns
 * @param source Source directory path
 * @param destination Destination directory path
 * @param excludes Patterns of files/directories to exclude
 */
export function copyDirectory(
  source: string,
  destination: string,
  excludes: string[] = [],
): void {
  if (!fs.existsSync(source)) {
    throw new Error(`Source directory does not exist: ${source}`);
  }

  // Convert glob patterns to RegExp for matching
  const excludePatterns = excludes.map(
    (pattern) => new RegExp(pattern.replace(/\*/g, ".*")),
  );

  /**
   * Checks if a file should be excluded based on patterns
   */
  const shouldExclude = (filePath: string): boolean => {
    return excludePatterns.some((pattern) => pattern.test(filePath));
  };

  /**
   * Recursively copies files and directories
   */
  const copyRecursive = (src: string, dest: string) => {
    const files = fs.readdirSync(src);

    files.forEach((file) => {
      if (shouldExclude(file)) return;

      // Use sanitizePath to prevent path traversal
      const srcPath = sanitizePath(src, file);
      const destPath = sanitizePath(dest, file);

      if (fs.statSync(srcPath).isDirectory()) {
        ensureDirectoryExists(destPath);
        copyRecursive(srcPath, destPath);
      } else {
        fs.copyFileSync(srcPath, destPath);
      }
    });
  };

  ensureDirectoryExists(destination);
  copyRecursive(source, destination);
}

/**
 * Writes content to a file, creating directories if needed
 * @param filePath Path to the file
 * @param content Content to write
 */
export function writeFileWithDirs(filePath: string, content: string): void {
  const dirPath = path.dirname(filePath);
  ensureDirectoryExists(dirPath);
  fs.writeFileSync(filePath, content);
}
