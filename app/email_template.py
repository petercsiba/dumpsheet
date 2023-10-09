# title, content
from typing import Optional

# title, content
full_template = """
<!DOCTYPE html>
<html>
<head>
  <!-- For overriding dark mode -->
  <meta name="color-scheme" content="light">
  <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #fdfefe; font-family: Arial, sans-serif;">

<!-- Main Layout -->
<table width="100%" cellspacing="0" cellpadding="0"
style="background-image: url('https://voxana-ai-static.s3.amazonaws.com/voxana-hero-background-white-553x843.jpg');
       background-position: bottom right; image-rendering: auto; background-repeat: no-repeat; background-size: cover;
       background-attachment: fixed;
       ">
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
      <table align="center" width="100%" cellspacing="0" cellpadding="10" style="margin-top: 30px; ">
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

# We do 96% to be mobile friendly
_content_begin = """
        <table align="center" width="96%" cellspacing="0" cellpadding="0"
                    style="max-width: 36rem; margin-top: 20px; border: 1px solid black; background-color: white;
                    border-radius: 12px;">
"""


def main_content_template(content, heading: Optional[str] = None):
    heading_html = ""
    if bool(heading):
        heading_html = """
            <div style="font-size: 18px; font-weight: bold; margin-bottom: 10px;">{heading}</div>
        """.format(
            heading=heading
        )

    return (
        _content_begin
        + """
            <tr>
              <td style="padding: 20px;">
                {heading_html}
                {content}
              </td>
            </tr>
          </table>
    """.format(
            heading_html=heading_html, content=content
        )
    )


# heading, rows
table_template = (
    _content_begin
    + """
        <tr>
          <td style="padding: 20px;">
            <div style="font-size: 18px; font-weight: bold; margin-bottom: 10px;">{heading}</div>

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
)

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
        content=main_content_template(
            heading=sub_title,
            content=content_text,
        ),
    )
