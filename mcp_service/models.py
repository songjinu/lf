from pydantic import BaseModel, Field
from typing import Optional

class ReportRequest(BaseModel):
    report_type: str = Field(..., description="Type of report to generate, e.g., 'weekly', 'monthly'")
    recipient_email: Optional[str] = Field(None, description="Email address to send the report to, if combined with email tool")

class ReportResponse(BaseModel):
    report_id: str = Field(..., description="Unique ID for the generated report")
    status: str = Field(..., description="Status of the report generation")
    file_path: Optional[str] = Field(None, description="Path to the generated report file (mocked)")
    message: Optional[str] = Field(None, description="Additional messages or error details")

class EmailRequest(BaseModel):
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Subject of the email")
    body: str = Field(..., description="Body content of the email")
    attachment_path: Optional[str] = Field(None, description="Path to a file to attach (mocked)")

class EmailResponse(BaseModel):
    email_id: str = Field(..., description="Unique ID for the sent email")
    status: str = Field(..., description="Status of the email sending process")
    message: Optional[str] = Field(None, description="Additional messages or error details")

class ToolProgress(BaseModel):
    task_id: str
    step: str
    status: str
    details: Optional[str] = None
