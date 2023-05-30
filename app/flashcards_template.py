def get_flashcard_template():
    return """<!doctype html>
<html lang="en">
<head>
    <title>{{ title }}</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">

    <link href="https://fonts.googleapis.com/css?family=Poppins:300,400,500,600,700,800,900" rel="stylesheet">

    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/font-awesome/4.7.0/css/font-awesome.min.css">
    <link rel="stylesheet" href="css/style.css">
    <style>
        .gpt-nav {
          display: flex;
          justify-content: space-around;
        }

        .gpt-nav-button {
          padding: 10px;
          cursor: pointer;
        }

        .gpt-active-button {
          background-color: #007BFF;
          color: white;
        }

        .gpt-content {
          margin-top: 20px;
          border: 1px solid #000;
          padding: 10px;
        }
    </style>
    <script type="text/javascript">
        // Requires gpt-content, gpt-nav-button and linked id=contentId
        function gptShowContent(contentId, clickedButton) {
          console.log(contentId)
          // Hide all content
          var contents = document.getElementsByClassName('gpt-content');
          for (var i = 0; i < contents.length; i++) {
            contents[i].style.display = 'none';
          }

          // Remove the active-button class from all buttons
          var buttons = document.getElementsByClassName('gpt-nav-button');
          for (var i = 0; i < buttons.length; i++) {
            buttons[i].classList.remove('gpt-active-button');
          }

          // Show the clicked content
          var content = document.getElementById(contentId);
          content.style.display = 'block';

          // Add the active-button class to the clicked button
          clickedButton.classList.add('gpt-active-button');
        }
        function copyToClipboard(id) {
          var content = document.getElementById(id).innerText;
          var el = document.createElement('textarea');
          el.value = content;
          el.setAttribute('readonly', '');
          el.style.position = 'absolute';
          el.style.left = '-9999px';
          document.body.appendChild(el);
          el.select();
          document.execCommand('copy');
          document.body.removeChild(el);
        }
    </script>
</head>
<body>

<div class="wrapper d-flex align-items-stretch">
    <nav id="sidebar">
        <div class="custom-menu">
            <button type="button" id="sidebarCollapse" class="btn btn-primary">
                <i class="fa fa-bars"></i>
                <span class="sr-only">Toggle Menu</span>
            </button>
        </div>
        <h1><a href="index.html" class="logo">{{ project_name }}</a></h1>
        <ul class="list-unstyled components mb-5">
            <!-- <li class="active"> -->
    {{ person_head.begin }}
            <li class="gpt-nav-button {{ person_head.style_display }}"
                onclick="gptShowContent('{{ person_head.element_id }}', this)">
                <span class="fa"></span>
                {{ person_head.name }}
            </li>
    {{ person_head.end }}
        </ul>

    </nav>

    <!-- Page Content  -->
    <div id="content" class="p-4 p-md-5 pt-5">
    {{ person_body.begin }}
        <div id="{{ person_body.element_id }}"
            class="gpt-content"
            style="display: person_body.style_display;">
            <h2 class="mb-4">{{ person_body.name }}</h2>
            <ul>
                <li><strong>Priority</strong>: {{ person_body.priority }}</li>
                <li><strong>Industry</strong>: {{ person_body.industry }}</li>
                <li><strong>Vibes</strong>: {{ person_body.vibes }}</li>
                <li><strong>From</strong>: {{ person_body.from }}</li>
                <li><strong>Contact Info</strong>: {{ person_body.contact_info }}</li>
            </ul>
            <h2 class="mb-4">Suggested follow ups</h2>

            {{ follow_ups.begin }}
            <h4>Follow up: {{ follow_ups.message_type }}</h4>
            <p id="{{ follow_ups.element_id }}">
                {{ follow_ups.outreach_draft }}
                <button onclick="copyToClipboard('{{ follow_ups.element_id }}')">&#128203; Copy</button>
            </p>
            {{ follow_ups.end }}

            <h2 class="mb-4">Original transcript</h2>
            <p id="{{ person_body.element_id}}_transcript">
                {{ person_body.transcript }}
            </p>
        </div>
    {{ person_body.end }}
    </div>
</div>

<script src="js/jquery.min.js"></script>
<script src="js/popper.js"></script>
<script src="js/bootstrap.min.js"></script>
<script src="js/main.js"></script>
</body>
</html>
    """