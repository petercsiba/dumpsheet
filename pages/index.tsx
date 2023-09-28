// TODO(P1, devx): Setup eslint with https://legacy.reactjs.org/docs/hooks-rules.html#eslint-plugin
import dynamic from 'next/dynamic'
import Head from 'next/head'
import Image from 'next/image';
import {useSession, useSupabaseClient} from '@supabase/auth-helpers-react'
import {AccountProvider} from "@/contexts/AccountContext";
import ConnectHubspotButton from "@/components/ConnectHubspotButton";

const VoiceRecorderWithNoSSR = dynamic(() => import('@/components/VoiceRecorder'), {
    ssr: false
})

export default function Home() {
    const session = useSession()
    const supabase = useSupabaseClient()

    return (
        <>
            <AccountProvider>
                <Head>
                    <title>Voxana AI - Your Executive Assistant</title>
                    <meta name="description" content="Voxana AI - Your Voice, Turned into Action"/>
                    <meta name="viewport" content="width=device-width, initial-scale=1"/>
                    <link rel="icon" href="/favicon.ico"/>
                </Head>
                <div className="w-full h-full bg-gray-200">
                    <div className="min-w-full min-h-screen flex items-center justify-center">
                        <div className="w-full h-full flex justify-center items-center p-4">
                            <div
                                className="w-full h-full sm:h-auto sm:w-2/5 max-w-sm p-5 bg-white shadow flex flex-col text-base">

                                <div className="flex flex-col items-center py-4">
                                    <h2 className="text-3xl font-bold text-gray-800 leading-tight tracking-wide text-center">
                                        Tell me about your meeting
                                    </h2>
                                </div>
                                <div className="pt-4">
                                    <VoiceRecorderWithNoSSR/>
                                </div>
                                <div className="flex flex-col items-center py-8">
                                    <Image
                                        src="/images/voxana-ai-logo-transparent.png"
                                        alt="Voxana AI Logo"
                                        width={150}
                                        height={30}
                                    />
                                </div>

                            </div>
                        </div>
                    </div>
                    <ConnectHubspotButton></ConnectHubspotButton>
                </div>
            </AccountProvider>
        </>
    )
}
