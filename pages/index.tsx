import dynamic from 'next/dynamic'
import Head from 'next/head'
import Image from 'next/image';
import { useSession, useSupabaseClient } from '@supabase/auth-helpers-react'
import {Auth, ThemeSupa} from '@supabase/auth-ui-react'
import TodoList from '@/components/TodoList'

const VoiceRecorderWithNoSSR = dynamic(() => import('@/components/VoiceRecorder'), {
    ssr: false
})

import VoiceRecorder from '@/components/VoiceRecorder'

export default function Home() {
  const session = useSession()
  const supabase = useSupabaseClient()

  return (
    <>
      <Head>
        <title>Voxana AI - Your Executive Sidekick</title>
        <meta name="description" content="Voxana AI - Your Voice, Turned into Action" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>
      <div className="w-full h-full bg-gray-200">
          <div className="min-w-full min-h-screen flex items-center justify-center">
              <div className="w-full h-full flex justify-center items-center p-4">
                  <div className="w-full h-full sm:h-auto sm:w-2/5 max-w-sm p-5 bg-white shadow flex flex-col text-base">
                      <div className="flex flex-col items-center py-8">
                          <Image
                              src="/images/tell-me-what-to-draft.png"
                              alt="tell me what to draft heading"
                              width={300}
                              height={30}
                          />
                      </div>
                      {/*
                    <span className="font-sans font-normal text-3xl text-black text-center pb-2 mb-1 mx-4 align-center">
                      Tell me what to draft
                    </span>
                    */}
                      {/*
                    <span className="font-sans font-light text-2xl text-left pb-2 mb-1 mx-4">
                        Examples
                    </span>
                      <div className="pl-8">
                        <ul className="list-disc">
                            <li>Email replies you procrastinate on</li>
                            <li>Follow ups from your recent encounters</li>
                        </ul>
                      </div>
                      */}
                      <div className="pt-4">
                        <VoiceRecorderWithNoSSR />
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
          {/*
        {!session ? (
          <div className="min-w-full min-h-screen flex items-center justify-center">
            <div className="w-full h-full flex justify-center items-center p-4">
              <div className="w-full h-full sm:h-auto sm:w-2/5 max-w-sm p-5 bg-white shadow flex flex-col text-base">
                  {//TODO(p0, ux): Replace with Magic-link https://supabase.com/docs/guides/auth/auth-magic-link}
                <span className="font-sans text-4xl text-center pb-2 mb-1 border-b mx-4 align-center">
                  Login
                </span>
                <Auth supabaseClient={supabase} appearance={{ theme: ThemeSupa }} theme="light" />
              </div>
            </div>
          </div>
        ) : (
          <div
            className="w-full h-full flex flex-col justify-center items-center p-4"
            style={{ minWidth: 250, maxWidth: 600, margin: 'auto' }}
          >
            <TodoList session={session} />
            <button
              className="btn-black w-1/2 mt-12"
              onClick={async () => {
                const { error } = await supabase.auth.signOut()
                if (error) console.log('Error logging out:', error.message)
              }}
            >
              Logout
            </button>
          </div>
        )}
                */}
      </div>
    </>
  )
}
