import { Html, Head, Main, NextScript } from 'next/document'

export default function Document() {
  return (
    <Html lang="en">
      <Head />
      <body>
        <Main />
        <NextScript />
        {/* Start of HubSpot Embed Code */}
        <script type="text/javascript" id="hs-script-loader" async defer src="//js-na1.hs-scripts.com/40211602.js"></script>
      </body>
    </Html>
  )
}
