import Image from 'next/image';
import dynamic from "next/dynamic";
import {AccountProvider} from "@/contexts/AccountContext";
import ConnectHubspotButton from "@/components/ConnectHubspotButton";
import Head from "next/head";
import Banner from "@/components/Banner";

const VoiceRecorderWithNoSSR = dynamic(() => import('@/components/VoiceRecorder'), {
  ssr: false
})

export default function Home() {
    const isProduction = process.env.NODE_ENV === 'production';

  return (
      <AccountProvider>
          <Head>
              {isProduction && (
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

              <title>Voxana AI - Voice Data Entry into your CRM</title>
              <meta name="description" content="Voxana AI - Talkers gonna talk. Voxana creates contacts, follow ups and notes just from your voice. Throw away the keyboard and go for a walk-and-talk with your CRM!"/>
              <meta name="viewport" content="width=device-width, initial-scale=1"/>
              <link rel="icon" href="/favicon.ico"/>
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
            .middle-box {
              width: 90%;
              height: auto;
            }
          }
        `}</style>

          <div className="bg-[#fdfefe] bg-bottom-right bg-cover bg-fixed h-screen w-full relative"
               style={{ backgroundImage: 'url("/images/voxana-hero-background.png")' }}>
             <Banner></Banner>
              <div
                  className="flex flex-col items-center justify-center gap-6 px-10 pt-10 pb-4 absolute top-[45%] left-1/2 transform -translate-x-1/2 -translate-y-1/2 md:w-96 h-144 rounded-lg border border-black bg-white"
                  style={{ width: '80%', maxWidth: '24rem' }}
                  >
                  <VoiceRecorderWithNoSSR/>
              </div>

              <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 flex items-center space-x-2 font-montserrat">
                  <div className="w-full p-4 flex items-center justify-center">
                      <ConnectHubspotButton></ConnectHubspotButton>
                  </div>
              </div>
          </div>

      </AccountProvider>
  );
};
