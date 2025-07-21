#!/usr/bin/env python3
import json
import os
import sys
from typing import Dict, List, Any, Optional

def convert_openapi_to_service_model(openapi_path: str, service_name: str = "ccf") -> Dict[str, Any]:
    """
    Convert an OpenAPI 3.0 specification to an AWS service model format
    that can be used with `aws configure add-model`.
    """
    # Load the OpenAPI spec
    with open(openapi_path, 'r', encoding="utf-8") as f:
        openapi_spec = json.load(f)
    
    # Get the API Gateway endpoint URL from the OpenAPI spec
    api_gateway_url = None
    if "servers" in openapi_spec and len(openapi_spec["servers"]) > 0:
        api_gateway_url = openapi_spec["servers"][0].get("url")
    
    # Create the basic service model structure
    service_model = {
        "version": "2.0",
        "metadata": {
            "apiVersion": openapi_spec.get("info", {}).get("version", "2025-06-01"),
            "endpointPrefix": service_name,
            "jsonVersion": "1.1",
            "protocol": "rest-json",
            "serviceFullName": openapi_spec.get("info", {}).get("title", "Custom Connector Framework"),
            "serviceId": service_name,
            "signatureVersion": "v4",
            "uid": f"{service_name}-2025-06-01",
            "signingName": "execute-api"
        },
        "operations": {},
        "shapes": {},
        "documentation": openapi_spec.get("info", {}).get("description", "Custom Connector Framework API")
    }
    
    # Add endpoint information if available
    if api_gateway_url:
        # Extract the hostname from the URL
        import re
        hostname_match = re.search(r'https?://([^/]+)', api_gateway_url)
        if hostname_match:
            hostname = hostname_match.group(1)
            service_model["metadata"]["endpoint"] = hostname
            service_model["metadata"]["hostname"] = hostname
    
    # Add basic shapes
    service_model["shapes"]["String"] = {"type": "string"}
    service_model["shapes"]["Integer"] = {"type": "integer"}
    service_model["shapes"]["Boolean"] = {"type": "boolean"}
    service_model["shapes"]["Timestamp"] = {"type": "timestamp"}
    service_model["shapes"]["Float"] = {"type": "float"}
    service_model["shapes"]["Document"] = {"type": "structure", "document": True}
    
    # Operation name mapping
    operation_name_mapping = {
        ("POST", "/api/v1/custom-connectors"): "CreateCustomConnector",
        ("GET", "/api/v1/custom-connectors/{connector_id}"): "GetCustomConnector",
        ("PUT", "/api/v1/custom-connectors/{connector_id}"): "UpdateCustomConnector",
        ("GET", "/api/v1/custom-connectors"): "ListCustomConnectors",
        ("DELETE", "/api/v1/custom-connectors/{connector_id}"): "DeleteCustomConnector",
        ("POST", "/api/v1/custom-connectors/{connector_id}/jobs"): "StartCustomConnectorJob",
        ("GET", "/api/v1/custom-connectors/{connector_id}/jobs"): "ListCustomConnectorJobs",
        ("POST", "/api/v1/custom-connectors/{connector_id}/jobs/{job_id}/stop"): "StopCustomConnectorJob",
        ("POST", "/api/v1/custom-connectors/{connector_id}/documents"): "BatchPutCustomConnectorDocuments",
        ("GET", "/api/v1/custom-connectors/{connector_id}/documents"): "ListCustomConnectorDocuments",
        ("DELETE", "/api/v1/custom-connectors/{connector_id}/documents"): "BatchDeleteCustomConnectorDocuments",
        ("GET", "/api/v1/custom-connectors/{connector_id}/checkpoint"): "GetCustomConnectorCheckpoint",
        ("PUT", "/api/v1/custom-connectors/{connector_id}/checkpoint"): "PutCustomConnectorCheckpoint",
        ("DELETE", "/api/v1/custom-connectors/{connector_id}/checkpoint"): "DeleteCustomConnectorCheckpoint"
    }
    
    # Process paths and operations
    for path, path_item in openapi_spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                continue
                
            # Get the operation name from the mapping
            operation_name = operation_name_mapping.get((method.upper(), path))
            if not operation_name:
                continue
            
            # Create request and response shapes
            input_shape_name = f"{operation_name}Request"
            output_shape_name = f"{operation_name}Response"
            
            # Create operation entry
            service_model["operations"][operation_name] = {
                "name": operation_name,
                "http": {
                    "method": method.upper(),
                    "requestUri": path,
                    "responseCode": 200
                },
                "documentation": operation.get("description", f"{operation_name} operation")
            }
            
            # Process parameters and create input shape
            input_shape = {"type": "structure", "required": [], "members": {}}
            
            # Process path parameters
            path_params = [p for p in operation.get("parameters", []) if p.get("in") == "path"]
            for param in path_params:
                param_name = param.get("name")
                param_schema = param.get("schema", {})
                param_type = param_schema.get("type", "string")
                
                # Add to required list if required
                if param.get("required", False):
                    input_shape["required"].append(param_name)
                
                # Add member to input shape
                input_shape["members"][param_name] = {
                    "shape": map_type_to_shape(param_type),
                    "location": "uri",
                    "locationName": param_name,
                    "documentation": param.get("description", f"The {param_name} parameter")
                }
            
            # Process query parameters
            query_params = [p for p in operation.get("parameters", []) if p.get("in") == "query"]
            for param in query_params:
                param_name = param.get("name")
                param_schema = param.get("schema", {})
                param_type = param_schema.get("type", "string")
                
                # Add to required list if required
                if param.get("required", False):
                    input_shape["required"].append(param_name)
                
                # Add member to input shape
                input_shape["members"][param_name] = {
                    "shape": map_type_to_shape(param_type),
                    "location": "querystring",
                    "locationName": param_name,
                    "documentation": param.get("description", f"The {param_name} parameter")
                }
            
            # Process request body if it exists
            if operation.get("requestBody"):
                content_type = next(iter(operation["requestBody"].get("content", {})), None)
                if content_type and content_type == "application/json":
                    schema_ref = operation["requestBody"]["content"][content_type].get("schema", {}).get("$ref")
                    
                    if schema_ref:
                        # Extract schema name from reference
                        schema_name = schema_ref.split("/")[-1]
                        schema = openapi_spec["components"]["schemas"][schema_name]
                        
                        # Create shapes for the schema properties
                        for prop_name, prop_schema in schema.get("properties", {}).items():
                            prop_shape_name = get_shape_for_property(prop_name, prop_schema, schema_name, service_model["shapes"])
                            
                            # Add to required list if the property is required in the schema
                            if prop_name in schema.get("required", []):
                                input_shape["required"].append(prop_name)
                            
                            # Add member to input shape as a top-level parameter
                            input_shape["members"][prop_name] = {
                                "shape": prop_shape_name,
                                "documentation": prop_schema.get("description", f"The {prop_name} property")
                            }
            
            # Add input shape to service model if it has members
            if input_shape["members"]:
                service_model["shapes"][input_shape_name] = input_shape
                service_model["operations"][operation_name]["input"] = {"shape": input_shape_name}
            
            # Process responses
            for status_code, response in operation.get("responses", {}).items():
                if status_code.startswith("2"):  # 2xx responses
                    service_model["operations"][operation_name]["http"]["responseCode"] = int(status_code)
                    
                    if "content" in response and "application/json" in response["content"]:
                        schema_ref = response["content"]["application/json"].get("schema", {}).get("$ref")
                        
                        if schema_ref:
                            # Extract schema name from reference
                            schema_name = schema_ref.split("/")[-1]
                            schema = openapi_spec["components"]["schemas"][schema_name]
                            
                            # Create shapes for the schema
                            process_schema(schema, schema_name, service_model["shapes"])
                            
                            # Create output shape that directly maps to the response schema
                            output_shape = {"type": "structure", "members": {}}
                            
                            # For other operations, extract properties from the schema
                            # and add them directly to the output shape
                            for prop_name, prop_schema in schema.get("properties", {}).items():
                                output_shape["members"][prop_name] = {
                                    "shape": get_shape_for_property(prop_name, prop_schema, schema_name, service_model["shapes"]),
                                    "documentation": prop_schema.get("description", f"The {prop_name} property")
                                }
                            
                            # Add output shape to service model
                            service_model["shapes"][output_shape_name] = output_shape
                            service_model["operations"][operation_name]["output"] = {"shape": output_shape_name}
                    
                    break  # Only process the first successful response
            
            # Process error responses
            error_shapes = []
            for status_code, response in operation.get("responses", {}).items():
                if not status_code.startswith("2"):  # Non-2xx responses
                    error_shape_name = f"{operation_name}Error{status_code}"
                    error_shape = {
                        "type": "structure",
                        "members": {
                            "message": {
                                "shape": "String",
                                "documentation": "Error message"
                            }
                        },
                        "error": {
                            "httpStatusCode": int(status_code)
                        },
                        "exception": True,
                        "documentation": response.get("description", f"Error {status_code}")
                    }
                    
                    # Add error shape to service model
                    service_model["shapes"][error_shape_name] = error_shape
                    error_shapes.append({"shape": error_shape_name})
            
            # Add error shapes to operation
            if error_shapes:
                service_model["operations"][operation_name]["errors"] = error_shapes
    
    return service_model

def map_type_to_shape(openapi_type: str) -> str:
    """Map OpenAPI types to AWS service model shape types."""
    type_mapping = {
        "string": "String",
        "integer": "Integer",
        "boolean": "Boolean",
        "number": "Float",
        "object": "Document",
        "array": "List"
    }
    return type_mapping.get(openapi_type, "String")

def get_shape_for_property(prop_name: str, prop_schema: Dict[str, Any], parent_shape_name: str, shapes: Dict[str, Any]) -> str:
    """Get or create a shape for a property."""
    prop_type = prop_schema.get("type")
    
    if prop_type == "object":
        # Create a shape for the object
        shape_name = f"{parent_shape_name}{prop_name.title()}"
        if shape_name not in shapes:
            shapes[shape_name] = create_object_shape(prop_schema, shape_name, shapes)
        return shape_name
    elif prop_type == "array":
        # Create a shape for the array
        shape_name = f"{parent_shape_name}{prop_name.title()}List"
        if shape_name not in shapes:
            shapes[shape_name] = create_array_shape(prop_schema, shape_name, shapes)
        return shape_name
    else:
        # Use a primitive type
        return map_type_to_shape(prop_type)

def create_object_shape(schema: Dict[str, Any], shape_name: str, shapes: Dict[str, Any]) -> Dict[str, Any]:
    """Create a shape for an object schema."""
    shape = {
        "type": "structure",
        "required": schema.get("required", []),
        "members": {}
    }
    
    for prop_name, prop_schema in schema.get("properties", {}).items():
        shape["members"][prop_name] = {
            "shape": get_shape_for_property(prop_name, prop_schema, shape_name, shapes),
            "documentation": prop_schema.get("description", f"The {prop_name} property")
        }
    
    return shape

def create_array_shape(schema: Dict[str, Any], shape_name: str, shapes: Dict[str, Any]) -> Dict[str, Any]:
    """Create a shape for an array schema."""
    items_schema = schema.get("items", {})
    items_type = items_schema.get("type")
    
    if items_type == "object":
        # Create a shape for the array items
        item_shape_name = f"{shape_name}Item"
        shapes[item_shape_name] = create_object_shape(items_schema, item_shape_name, shapes)
        
        return {
            "type": "list",
            "member": {
                "shape": item_shape_name
            }
        }
    else:
        # Use a primitive type for the array items
        return {
            "type": "list",
            "member": {
                "shape": map_type_to_shape(items_type)
            }
        }

def process_schema(schema: Dict[str, Any], schema_name: str, shapes: Dict[str, Any]) -> None:
    """Process a schema and add it to the shapes dictionary."""
    if schema_name in shapes:
        return  # Already processed
    
    if schema.get("type") == "object":
        shapes[schema_name] = create_object_shape(schema, schema_name, shapes)
    elif schema.get("type") == "array":
        shapes[schema_name] = create_array_shape(schema, schema_name, shapes)
    else:
        shapes[schema_name] = {"type": map_type_to_shape(schema.get("type"))}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python openapi_to_service_model.py <openapi_file> [service_name]")
        sys.exit(1)
    
    openapi_path = sys.argv[1]
    service_name = sys.argv[2] if len(sys.argv) > 2 else "ccf"
    
    service_model = convert_openapi_to_service_model(openapi_path, service_name)
    
    # Write the service model to a file
    output_path = f"{service_name}-service-model.json"
    with open(output_path, 'w', encoding="utf-8") as f:
        json.dump(service_model, f, indent=2)
    
    print(f"Service model created at: {output_path}")
    print(f"To add this model to AWS CLI, run:")
    print(f"aws configure add-model --service-model file://{output_path} --service-name {service_name}")
