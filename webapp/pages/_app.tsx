// TODO(P0, monitoring): Vercel has some free monitoring tools, add the setup somewhere

import '@/styles/app.css'
import type { AppProps } from 'next/app'

export default function App({ Component, pageProps }: AppProps) {
  return (
    <Component {...pageProps} />
  )
}
