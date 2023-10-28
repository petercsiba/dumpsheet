from typing import Optional

# title, content
_full_template = """
<!DOCTYPE html>
<html>
<head>
  <!-- For overriding dark mode -->
  <meta name="color-scheme" content="light">
  <title>{title}</title>
</head>

<body style="margin: 0; padding: 0; background-color: #fdfefe; font-family: Arial, sans-serif;">

<!-- Pre-header - for now just use the title -->
<div style="display: none; max-height: 0px; overflow: hidden;">
{pre_header}
</div>

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
      <table align="center" width="96%" cellspacing="0" cellpadding="0"
                    style="max-width: 36rem; margin-top: 30px;">
        <tr>
          <td>
            <table align="center" cellspacing="0" cellpadding="14"
                style="background-color: white; border: 1px solid black; border-radius: 50px; width: auto;">
              <tr>
                <td align="center">
                  Thank you for using <b><a href="https://www.voxana.ai/">Voxana.ai</a></b>
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


def full_template(title: str, content: str, pre_header: Optional[str]):
    if pre_header is None:
        pre_header = title
    print(f"FILLING FULL_TEMPLATE {len(title)}, {len(content)}, {len(pre_header)}")
    return _full_template.format(title=title, content=content, pre_header=pre_header)


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


# extra_content_html should include <tr> ... </tr>
def table_template(heading, rows_html: str, extra_content_html: str):
    if len(str(extra_content_html)) > 5:
        extra_content_html = f"""
        <div style="height:1px; background-color:lightgray; margin-top:20px; margin-bottom:25px;"></div>
            {extra_content_html}
        """
    return (
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
              {rows_html}
            </table>
            {extra_content_html}
          </td>
        </tr>
      </table>
""".format(
            heading=heading,
            rows_html=rows_html,
            extra_content_html=extra_content_html,
        )
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
    return full_template(
        title=title,
        pre_header=sub_title,
        content=main_content_template(
            heading=sub_title,
            content=content_text,
        ),
    )


def button_template(text: str, href: str):
    return f"""
      <table align="center" cellspacing="0" cellpadding="14" style="border-radius: 50px; width: auto;
                background-color: black;">
        <tr>
          <td align="center">
            <a href="{href}" target="_blank" rel="noopener noreferrer" style="text-decoration: none; color: white;
                font-size: 18px; font-weight: 600; letter-spacing: 0.05em;">
              {text}
            </a>
          </td>
        </tr>
      </table>
    """
