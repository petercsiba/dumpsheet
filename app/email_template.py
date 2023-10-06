# title, content
from typing import Optional

full_template = """
<!DOCTYPE html>
<html>
<head>
  <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #fdfefe; font-family: Arial, sans-serif;">

<!-- Main Layout -->
<table width="100%" cellspacing="0" cellpadding="0"
style="background-image: url('https://voxana-ai-static.s3.amazonaws.com/voxana-hero-background-1634x1696.png');
       background-position: bottom right; background-size: cover;">
  <tr>
    <td>
      <!-- Logo and Demo button -->
      <table width="100%" cellspacing="0" cellpadding="10">
        <tr>
          <td style="text-align: left;">
            <a href="https://www.voxana.ai">
              <img src="https://voxana-ai-static.s3.amazonaws.com/voxana-logo-text-rectangle-930x174-transparent.png"
                   alt="Voxana AI Logo"
                   width="192"
              />
            </a>
          </td>
          <td style="text-align: right;">
            <a href="https://calendly.com/katka-voxana/30min?month=2023-10"
                style="background-color: black; color: white; padding: 10px 20px; text-decoration: none;
                       border-radius: 20px;">Book a demo</a>
          </td>
        </tr>
      </table>

      <!-- Heading -->
      <table align="center" cellspacing="0" cellpadding="10"
        style="background-color: white; border: 1px solid black; border-radius: 50px; width: auto;">
        <tr>
          <td style="font-size: 20px; text-align: center; font-weight: bold; color: black;">
            {title}
          </td>
        </tr>
      </table>

      <!-- add extra padding -->
      <table><tr><td></td></tr></table>

      <!-- Main Content with Table -->
      {content}

      <!-- Footer -->
      <table align="center" width="100%" cellspacing="0" cellpadding="10" style="margin-top: 100px; ">
        <tr>
          <td align="center" style="font-size: 16px; font-weight: bold;">
            <table align="center" cellspacing="0" cellpadding="10"
                style="background-color: white; border: 1px solid black; border-radius: 50px; width: auto;">
              <tr>
                <td style="text-align: center; font-weight: bold; color: black;">
                  Supported By
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td>
            <table align="center" cellspacing="0" cellpadding="12"
                style="background-color: white; border: 1px solid black; border-radius: 50px; width: auto;">
              <tr>
                <td align="center">
                  Thank you for using <b><a href="https://www.voxana.ai/">Voxana.ai</a></b> - your executive assistant
                </td>
              </tr>
              <tr>
                <td align="center">
                  <b>Got any questions?</b> Just hit reply - my human supervisors respond to all emails within 24 hours
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

</body>
</html>
"""

# heading, content
main_content_template = """
      <table align="center" width="80%" cellspacing="0" cellpadding="0"
        style="max-width: 36rem; margin-top: 20px; border: 1px solid black; background-color: white;
        border-radius: 12px;">
        <tr>
          <td style="padding: 20px;">
            <div style="font-size: 18px; font-weight: bold; margin-bottom: 10px;">{heading}</div>
            {content}
          </td>
        </tr>
      </table>
"""

# heading, rows
table_template = """
      <table align="center" width="80%" cellspacing="0" cellpadding="0"
        style="max-width: 36rem; margin-top: 20px; border: 1px solid black; background-color: white;
        border-radius: 12px;">
        <tr>
          <td style="padding: 20px;">
            <div style="font-size: 24px; font-weight: bold; margin-bottom: 10px;">{heading}</div>

            <!-- Two-column table for order information -->
            <table width="100%" cellspacing="0" cellpadding="10">
              <!-- <tr>
                <th align="left" style="border-bottom: 1px solid #ccc;"><strong>Field</strong></th>
                <th align="left" style="border-bottom: 1px solid #ccc;"><strong>Value</strong></th>
              </tr> -->
              {rows}
            </table>
          </td>
        </tr>
      </table>
"""

# label, value
table_row_template = """
              <tr>
                <td align="left"><strong>{label}</strong></td>
                <td align="left">{value}</td>
              </tr>
"""


def simple_email_body_html(
    title: str, content_text: str, sub_title: Optional[str] = None
) -> str:
    return full_template.format(
        title=title,
        content=main_content_template.format(
            heading=sub_title if bool(sub_title) else title,
            content=content_text,
        ),
    )
