"""
Utility functions for the Custom Connector Framework.

This module provides helper functions and utilities used throughout the framework,
including serialization and data transformation utilities.
"""

from enum import Enum


class JsonSerializer:
    """
    Utility class for serializing objects to JSON-compatible formats.

    This class handles special cases like Enum values, ensuring they are
    properly serialized to their string representations.
    """

    @staticmethod
    def _convert_enum_to_str(value: list | dict | str | Enum) -> list | dict | str:
        """
        Recursively convert Enum values to their string representations.

        This method handles nested structures like lists and dictionaries,
        ensuring all Enum values are properly converted.

        Args:
            value: The value to convert, which may be a list, dict, string, or Enum

        Returns:
            The converted value with all Enum instances replaced by their string values

        """
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, list):
            return [JsonSerializer._convert_enum_to_str(item) for item in value]
        if isinstance(value, dict):
            return {key: JsonSerializer._convert_enum_to_str(val) for key, val in value.items()}
        return value

    @staticmethod
    def serialize(value: dict) -> dict:
        """
        Serialize a dictionary containing Enum values to a JSON-compatible dictionary.

        This method ensures all Enum values are converted to their string representations,
        making the dictionary suitable for JSON serialization.

        Args:
            value (dict): The dictionary to serialize

        Returns:
            dict: A JSON-compatible dictionary with Enum values converted to strings

        """
        result = JsonSerializer._convert_enum_to_str(value)
        # Ensure we always return a dict as promised by the type annotation
        if isinstance(result, dict):
            return result
        # This should never happen given the input type, but for type safety
        return {}
