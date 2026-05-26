import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_reset_email(to_email: str, reset_link: str):
    """
    Sends a beautifully styled HTML password reset email via Mailpit (SMTP).
    """
    print("[MAIL] Connecting to Mailpit")
    try:
        # Establish connection to Mailpit
        server = smtplib.SMTP("localhost", 1025, timeout=5)
    except Exception as e:
        print(f"[MAIL] Connection to Mailpit failed: {e}")
        raise RuntimeError(f"Could not connect to the mail server (Mailpit): {e}")

    # Build the multipart message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset Your Password"
    msg["From"] = "no-reply@llms-generator.com"
    msg["To"] = to_email

    # Premium, highly styled HTML body
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reset Your Password</title>
        <style>
            body {{
                font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: #f4f5f7;
                color: #111111;
                margin: 0;
                padding: 0;
                -webkit-font-smoothing: antialiased;
            }}
            .email-wrapper {{
                width: 100%;
                background-color: #f4f5f7;
                padding: 48px 20px;
                box-sizing: border-box;
            }}
            .email-container {{
                max-width: 520px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
                overflow: hidden;
                border: 1px solid #e1e4e8;
            }}
            .email-header {{
                background-color: #000000;
                padding: 32px;
                text-align: center;
            }}
            .email-header h1 {{
                color: #ffffff;
                font-size: 24px;
                font-weight: 300;
                margin: 0;
                letter-spacing: -0.5px;
            }}
            .email-header span {{
                font-weight: 700;
                font-style: italic;
            }}
            .email-body {{
                padding: 40px 32px;
            }}
            .email-body h2 {{
                font-size: 20px;
                font-weight: 700;
                margin-top: 0;
                margin-bottom: 16px;
                color: #111111;
            }}
            .email-body p {{
                font-size: 15px;
                line-height: 1.6;
                color: #444444;
                margin-top: 0;
                margin-bottom: 24px;
            }}
            .btn-wrapper {{
                text-align: center;
                margin: 32px 0;
            }}
            .btn {{
                display: inline-block;
                background-color: #111111;
                color: #ffffff !important;
                text-decoration: none;
                padding: 14px 28px;
                font-size: 15px;
                font-weight: 600;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                transition: all 0.2s ease;
            }}
            .link-fallback {{
                font-size: 12px;
                color: #888888;
                word-break: break-all;
                margin-top: 32px;
                border-top: 1px solid #eaeaea;
                padding-top: 16px;
            }}
            .link-fallback a {{
                color: #0052cc;
                text-decoration: underline;
            }}
            .email-footer {{
                background-color: #fafbfc;
                padding: 24px 32px;
                text-align: center;
                border-top: 1px solid #eaeaea;
                font-size: 13px;
                color: #888888;
            }}
        </style>
    </head>
    <body>
        <div class="email-wrapper">
            <div class="email-container">
                <!-- Header -->
                <div class="email-header">
                    <h1>LLMS.txt <span>generator</span></h1>
                </div>
                
                <!-- Body -->
                <div class="email-body">
                    <h2>Password Reset Request</h2>
                    <p>We received a request to reset the password for your account. Click the button below to secure a new password for your account. This link will expire shortly.</p>
                    
                    <div class="btn-wrapper">
                        <a href="{reset_link}" target="_blank" class="btn">Reset Password</a>
                    </div>
                    
                    <p>If you did not request a password reset, you can safely ignore this email.</p>
                    
                    <div class="link-fallback">
                        If the button above doesn't work, copy and paste this URL into your browser:<br>
                        <a href="{reset_link}" target="_blank">{reset_link}</a>
                    </div>
                </div>
                
                <!-- Footer -->
                <div class="email-footer">
                    &copy; 2026 llms.txt generator. All rights reserved.
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    # Attach the HTML content
    msg.attach(MIMEText(html_content, "html"))

    try:
        print("[MAIL] Sending reset email")
        # Send the email
        server.sendmail(
            "no-reply@llms-generator.com",
            [to_email],
            msg.as_string()
        )
        print("[MAIL] Email sent successfully")
    except Exception as e:
        print(f"[MAIL] Failed to send email: {e}")
        raise RuntimeError(f"Failed to send email to {to_email}: {e}")
    finally:
        server.quit()