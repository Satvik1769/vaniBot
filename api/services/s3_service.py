"""S3 service for storing conversation logs and audio recordings."""
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.getenv("S3_CONVERSATION_BUCKET", "battery-smart-conversations")


class S3Service:
    """Service for uploading conversation logs to S3."""

    def __init__(self):
        self.bucket = S3_BUCKET_NAME
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize S3 client."""
        try:
            if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
                self.client = boto3.client(
                    's3',
                    region_name=AWS_REGION,
                    aws_access_key_id=AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
                )
            else:
                # Use default credentials (IAM role, env vars, etc.)
                self.client = boto3.client('s3', region_name=AWS_REGION)
            logger.info(f"S3 client initialized for bucket: {self.bucket}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            self.client = None

    def _generate_key(
        self,
        session_id: str,
        phone_number: str,
        file_type: str = "json"
    ) -> str:
        """Generate S3 key with organized folder structure."""
        now = datetime.utcnow()
        # Structure: conversations/YYYY/MM/DD/phone_number/session_id.json
        key = (
            f"conversations/{now.year}/{now.month:02d}/{now.day:02d}/"
            f"{phone_number}/{session_id}.{file_type}"
        )
        return key

    async def upload_conversation_log(
        self,
        session_id: str,
        phone_number: str,
        conversation_data: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Upload conversation log to S3.

        Args:
            session_id: Unique session identifier
            phone_number: Driver's phone number
            conversation_data: Full conversation data including turns, metadata

        Returns:
            Dict with bucket, key, and url if successful, None otherwise
        """
        if not self.client:
            logger.warning("S3 client not initialized, skipping upload")
            return None

        try:
            key = self._generate_key(session_id, phone_number, "json")

            # Add upload timestamp
            conversation_data["uploaded_at"] = datetime.utcnow().isoformat()

            # Convert to JSON
            json_data = json.dumps(conversation_data, indent=2, default=str)

            # Upload to S3
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json_data.encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'session_id': session_id,
                    'phone_number': phone_number,
                    'channel': conversation_data.get('channel', 'voice')
                }
            )

            # Generate URL
            url = f"https://{self.bucket}.s3.{AWS_REGION}.amazonaws.com/{key}"

            logger.info(f"Uploaded conversation log to S3: {key}")
            return {
                "bucket": self.bucket,
                "key": key,
                "url": url
            }

        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
            return None

    async def upload_audio_recording(
        self,
        session_id: str,
        phone_number: str,
        audio_data: bytes,
        content_type: str = "audio/wav"
    ) -> Optional[Dict[str, str]]:
        """
        Upload audio recording to S3.

        Args:
            session_id: Unique session identifier
            phone_number: Driver's phone number
            audio_data: Raw audio bytes
            content_type: Audio MIME type

        Returns:
            Dict with bucket, key, and url if successful, None otherwise
        """
        if not self.client:
            logger.warning("S3 client not initialized, skipping audio upload")
            return None

        try:
            extension = "wav" if "wav" in content_type else "mp3"
            key = self._generate_key(session_id, phone_number, extension)
            key = key.replace("conversations/", "recordings/")

            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=audio_data,
                ContentType=content_type,
                Metadata={
                    'session_id': session_id,
                    'phone_number': phone_number
                }
            )

            url = f"https://{self.bucket}.s3.{AWS_REGION}.amazonaws.com/{key}"

            logger.info(f"Uploaded audio recording to S3: {key}")
            return {
                "bucket": self.bucket,
                "key": key,
                "url": url
            }

        except Exception as e:
            logger.error(f"Error uploading audio to S3: {e}")
            return None

    async def get_conversation_log(
        self,
        key: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve conversation log from S3."""
        if not self.client:
            return None

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except Exception as e:
            logger.error(f"Error retrieving from S3: {e}")
            return None


# Singleton instance
s3_service = S3Service()


# Helper functions for easy access
async def upload_conversation_to_s3(
    session_id: str,
    phone_number: str,
    conversation_data: Dict[str, Any]
) -> Optional[Dict[str, str]]:
    """Upload conversation log to S3."""
    return await s3_service.upload_conversation_log(
        session_id, phone_number, conversation_data
    )


async def upload_audio_to_s3(
    session_id: str,
    phone_number: str,
    audio_data: bytes,
    content_type: str = "audio/wav"
) -> Optional[Dict[str, str]]:
    """Upload audio recording to S3."""
    return await s3_service.upload_audio_recording(
        session_id, phone_number, audio_data, content_type
    )