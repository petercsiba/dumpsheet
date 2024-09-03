"use client";
import dynamic from "next/dynamic";
import ConnectHubspotButton from "@/components/ConnectHubspotButton";
import Head from "next/head";
import Banner from "@/components/Banner";
import ErrorBoundary from "@/components/ErrorBoundary";

const VoiceRecorderWithNoSSR = dynamic(() => import('@/components/VoiceRecorder'), {
    ssr: false
})

export default function Home() {
    const isProduction = process.env.NODE_ENV === 'production';

    return (
        <>
            <Head>
                {/*TODO(P0, migration): We need to consolidate this with the app/layout.tsx */}
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

                <title>Dumpsheet - Voice Data Entry into your Excel Spreadsheet</title>
                <meta name="description"
                      content="Dumpsheet - Talkers gonna talk. Dumpsheet creates rows, sheets and notes just from your voice. Throw away the keyboard and go for a walk-and-talk with your Excel!"/>
                <meta name="viewport" content="width=device-width, initial-scale=1"/>
                <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
                <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
                <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
                <link rel="manifest" href="/site.webmanifest" />
            </Head>

            <style jsx>{`
              @media (max-width: 768px) {
                .top-navigation {
                  flex-direction: column;
                  align-items: start;
                  gap: 1rem;
                }

                .top-navigation div {
                  font-size: 18px;
                }

                .voxana-middle-box {
                  width: 80%;
                  min-width: 14rem;
                  max-width: 18rem;
                }

                @media (max-width: 768px) {
                  .voxana-middle-box {
                    width: 92%;
                  }
                }
              }
            `}</style>

            <div className="bg-[#fdfefe] bg-bottom-right bg-cover bg-fixed h-screen w-full relative"
                 style={{
                     backgroundImage: 'url("/images/voxana-hero-background-553x843.png")',
                     backgroundPosition: 'bottom right', imageRendering: 'auto',
                     backgroundRepeat: 'no-repeat', backgroundSize: 'cover', backgroundAttachment: 'fixed'
                 }}>
                <Banner></Banner>
                <div
                    className="flex flex-col items-center justify-center gap-6 px-4 py-6 absolute top-[22rem] left-1/2 transform -translate-x-1/2 -translate-y-1/2 rounded-lg border border-black bg-white voxana-middle-box"
                >
                    <ErrorBoundary>
                        <VoiceRecorderWithNoSSR/>
                    </ErrorBoundary>
                </div>
                {false && (<div
                    className="absolute bottom-2 left-1/2 transform -translate-x-1/2 flex items-center space-x-2 font-montserrat">
                    <div className="w-full px-4 py-1 flex items-center justify-center">
                        <ConnectHubspotButton></ConnectHubspotButton>
                    </div>
                </div>)
                }
            </div>
        </>
    );
};
