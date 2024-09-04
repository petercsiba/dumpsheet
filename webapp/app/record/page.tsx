"use client";
import dynamic from "next/dynamic";
import Banner from "@/components/Banner";
import ErrorBoundary from "@/components/ErrorBoundary";
import {RecorderState} from "@/app/record/components/VoiceRecorder";

const VoiceRecorderWithNoSSR = dynamic(() => import('@/app/record/components/VoiceRecorder'), {
    ssr: false
})

export default async function Index() {
    return (
        //<Banner></Banner>
        <ErrorBoundary>
            <VoiceRecorderWithNoSSR />
        </ErrorBoundary>
    );
};
