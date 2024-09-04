import Footer from "@/components/Footer";
import Navbar from "@/components/Navbar";
import { Toaster } from "@/components/ui/toaster";
import { Suspense } from "react";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/next"
import '@/styles/app.css'
import Head from "next/head";

export const metadata = {
    title: "Dumpsheets",
    description: "Transcribe audio into an Email or Excel spreadsheet",
};

export default function RootLayout({ children }: any) {
    const isProduction = process.env.NODE_ENV === 'production';

    return (
        <html lang="en">
        <Head>
            {isProduction && (
                // TODO(P1, compliance): We need to disclose this tracking */
                <>
                    <script async src="https://www.googletagmanager.com/gtag/js?id=G-5M87782QY3"></script>
                    <script dangerouslySetInnerHTML={{
                        __html: `
        window.dataLayer = window.dataLayer || [];
        function gtag(){dataLayer.push(arguments);}
        gtag('js', new Date());
        gtag('config', 'G-5M87782QY3');
      `
                    }}>
                    </script>
                </>
            )}

            <title>Dumpsheet - Audio into an Excel Spreadsheet</title>
            <meta name="description"
                  content="Dumpsheet - Talkers gonna talk. Dumpsheet creates rows, sheets and notes just from any audio. Throw away the keyboard and go for a walk-and-talk with your Excel!"/>
            <meta name="viewport" content="width=device-width, initial-scale=1"/>
            <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
            <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
            <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
            <link rel="manifest" href="/site.webmanifest" />
        </Head>
        <body className="min-h-screen flex flex-col">
        <section>
            <Suspense
                fallback={
                    <div className="flex w-full px-4 lg:px-40 py-4 items-center border-b text-center gap-8 justify-between h-[69px]" />
                }
            >
                <Navbar />
            </Suspense>
        </section>
        <main className="flex flex-1 flex-col items-center py-16">
            {children}
        </main>
        <Footer />
        <Toaster />
        <Analytics />
        <SpeedInsights />
        </body>
        </html>
    );
}
