import Image from 'next/image';
import dynamic from "next/dynamic";
import {AccountProvider} from "@/contexts/AccountContext";
import ConnectHubspotButton from "@/components/ConnectHubspotButton";
import Head from "next/head";

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
          <div className="bg-[#fdfefe] bg-bottom-right bg-no-repeat bg-auto bg-fixed h-screen w-full"
               style={{ backgroundImage: 'url("/images/voxana-hero-background.png")', height: 1650 }}>
            <div className="absolute top-8 left-8 flex items-center space-x-2">
              <div className="pr-8 pt-1 [-webkit-text-stroke:0.19px_#000000] [font-family:'Montserrat-SemiBold',Helvetica] font-semibold text-black text-[22.1px] tracking-[0] leading-[normal]">
                <a href="https://www.voxana.ai/">Voxana AI</a>
              </div>
              <div className="flex items-center space-x-8 font-medium text-black text-lg tracking-tight">
                <div>Features</div>
                <div>Use cases</div>
              </div>
            </div>
            <div className="absolute top-6 right-8 flex items-center space-x-2">
                <a href="https://calendly.com/katka-voxana/30min?month=2023-10" target="_blank" rel="noopener noreferrer">
                    <button className="flex items-center justify-center w-40 h-12 bg-black rounded-full font-semibold text-white text-lg tracking-tighter">
                        Book a demo
                    </button>
                </a>
                <div className="flex items-center justify-center w-12 h-12 bg-[#0000001a] rounded-full">
                <Image className="group-8" alt="Group" src="/images/figma/group-1000004834.png" width={30} height={30} />
              </div>
            </div>

            <div className="flex flex-col items-center justify-center gap-6 px-10 py-10 absolute top-[40%] left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-96 h-144 rounded-lg border border-black bg-white">
                <div className="text-center font-semibold text-black text-2xl tracking-normal leading-normal">
                    Tell me about your meeting
                </div>
                <div className="pt-4 flex items-center justify-center">
                    <VoiceRecorderWithNoSSR/>
                </div>
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
