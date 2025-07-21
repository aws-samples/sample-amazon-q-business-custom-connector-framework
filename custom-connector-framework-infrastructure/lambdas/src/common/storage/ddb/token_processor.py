"""Utility for encoding and decoding tokens."""

import base64


class TokenProcessor:
    """Utility class for encoding and decoding tokens."""

    @staticmethod
    def encode_token(token_str: str) -> str:
        """
        Encode a JSON string into a base64 token.

        Args:
            token_str: JSON string to encode

        Returns:
            str: Base64 encoded token

        """
        try:
            return base64.b64encode(token_str.encode("utf-8")).decode("utf-8")
        except Exception as error:
            raise ValueError("Failed to encode token") from error

    @staticmethod
    def decode_token(token: str) -> str | None:
        """
        Decode a base64 token back into a JSON string.

        Args:
            token: Base64 encoded token string

        Returns:
            Optional[str]: Decoded JSON string or None if decoding fails

        """
        try:
            return base64.b64decode(token).decode("utf-8")
        except Exception as error:
            raise ValueError("Failed to decode token") from error
