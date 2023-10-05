// TODO(P1, browser-compatibility): Mobile Safari displays a weirdly small <audio> tag
import {useEffect, useState} from 'react'
import RecordRTC from 'recordrtc'
import Image from 'next/image'
// https://uxwing.com/stop-button-red-icon/
import MicrophoneIcon from '../public/images/icons/microphone-button-green-icon.svg'
import MicrophoneIconHover from '../public/images/icons/microphone-button-green-hover-icon.png'
import StopIcon from '../public/images/icons/stop-button-red-icon.svg'
import CollectEmailProcessingInfo from "@/components/CollectEmailProcessingInfo";
import {useAccount} from "@/contexts/AccountContext";

const PRESIGNED_URL = 'https://api.voxana.ai/upload/voice';
const UPLOAD_TIMEOUT = 30000;
const MIN_DURATION = Number(process.env.NEXT_PUBLIC_VOICE_RECORDER_MIN_DURATION_SECONDS) || 10;
const SHORT_RECORDING_TIMEOUT = 7000;

const RecorderState = {
    WELCOME: 'welcome',
    RECORDING: 'recording',
    UPLOADING: 'uploading',
    SUCCESS: 'success',
    FAILURE: 'failure',
    TOO_SHORT: 'too_short'
};

const formatDuration = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
};

const HeadingText = ({text}) => (
    <div id="upload-status"
         className="text-center font-semibold text-black text-2xl tracking-normal leading-normal pb-5">
        {text}
    </div>
)

const WelcomeState = ({onStartRecording}) => {
    const [imageSrc, setImageSrc] = useState(MicrophoneIcon);

    return (
        <>
            <HeadingText text={"Tell Me About Your Meeting"} />
            <div className="flex items-center justify-center">
                <button
                    className="btn-white p-0 hover:bg-gray-100"
                    onClick={onStartRecording}
                >
                    <div
                        className="inline-block"
                        onMouseEnter={() => {
                            setImageSrc(MicrophoneIconHover);  // Hover image
                        }}
                        onMouseLeave={() => {
                            setImageSrc(MicrophoneIcon);  // Default image
                        }}
                    >
                        <Image
                            priority
                            src={imageSrc}
                            alt="Start your voice recording"
                            width={100}
                            height={100}
                        />
                    </div>
                    <div>
                        Start
                    </div>
                </button>
            </div>
        </>
    )
}

const RecordingState = ({onStopRecording, elapsedTime}) => (
    <>
        <HeadingText text={"Recording ..."}/>
        <div className="flex flex-col items-center justify-center">
            <button className="btn-white p-0 hover:bg-gray-100" onClick={onStopRecording}>
                <div className="bg-white-500 p-2 inline-block">
                    <Image
                        priority
                        src={StopIcon}
                        alt="Stop and upload recording"
                        width={50}
                        height={50}
                    />
                </div>
                <div>
                    Stop
                </div>
            </button>
            <div className="mt-2">
                <p>{formatDuration(elapsedTime)}</p>
            </div>
        </div>
    </>
);

const UploadingState = () => (
    <HeadingText text={"Uploading ..."} />
);

const SuccessState = ({collectEmail, existingEmail, accountId}) => (
    <>
        <HeadingText text={"Upload was successful!"}></HeadingText>
        <CollectEmailProcessingInfo collectEmail={collectEmail} existingEmail={existingEmail}
                                    accountId={accountId}/>
    </>
)

const FailureState = ({audioURL, failureMessage}) => {
    const fileName = `voxana-audio-recording-${Date.now()}.webm`;

    return (
        <>
            <HeadingText text={"Failed to Upload Recording"}></HeadingText>
            <div className="bg-white-500 p-2 inline-block">
                <p className="py-2">Please, download the file and send it to ai@voxana.ai</p>
                <div className="flex justify-center">
                    <a href={audioURL} download={fileName}
                       className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 focus:outline-none">
                        Download Recording
                    </a>
                </div>
            </div>
            <div>
                Please send this error to support@voxana.ai: ${failureMessage}
            </div>
        </>
    );
};

const TooShortState = () => (
    <div className="flex-col">
        <HeadingText text={"Please, Tell Me More"}/>
        <div className="py-2">Your recording needs to be longer than {MIN_DURATION} seconds, please try again.</div>
        <div>(This page will auto-refresh in a bit)</div>
    </div>
);

// setUploadStatus(`Please try again or send this to support@voxana.ai: ${error}`);


export default function VoiceRecorder() {
    const [recorderState, setRecorderState] = useState(RecorderState.WELCOME);
    const [failureMessage, setFailureMessage] = useState(null);
    const [stream, setStream] = useState(null);
    const [recording, setRecording] = useState(null);
    const [audioURL, setAudioURL] = useState(null);
    const [recordingStartTime, setRecordingStartTime] = useState(null);
    const [recordingElapsedTime, setRecordingElapsedTime] = useState(0);
    const [collectEmail, setCollectEmail] = useState(null);
    const [existingEmail, setExistingEmail] = useState(null);
    const {accountId, setAccountId} = useAccount();


    useEffect(() => {
        let interval = null;

        if (recording) {
            interval = setInterval(() => {
                const secondsElapsed = (Date.now() - recordingStartTime) / 1000;
                setRecordingElapsedTime(secondsElapsed);
            }, 1000);
        } else {
            clearInterval(interval);
            setRecordingElapsedTime(null);
        }

        return () => clearInterval(interval);
    }, [recording, recordingStartTime]);

    // To fully release the media recording from the browser - as otherwise it shows a red mike "recording".
    const fullyReleaseMike = () => {
        console.log(`fullyReleaseMike for stream ${stream}`)
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        setRecording(null)
    };
    // TODO: This might need more work through `useRef`
    // useEffect(() => {
    // 	return () => fullyReleaseMike()
    // }, []);

    const startRecording = async () => {
        if (typeof window === 'undefined') {
            console.error('Recording is not supported on the server.')
            return
        }
        console.log(`startRecording`)
        setRecorderState(RecorderState.RECORDING)
        try {
            // TODO(P1, hack): setTimeout for the demo to refresh that part of the screen
            // * The theory is that requesting the mike blocks syncing with quick-time
            setTimeout(() => {
                console.log("delay some to update the button")
            }, 200); // 200ms delay

            const stream = await navigator.mediaDevices.getUserMedia({audio: true, video: false})
            const recorder = new RecordRTC(stream, {
                type: 'audio',
                mimeType: 'audio/webm'
            })

            console.log("setRecording")
            setRecordingStartTime(Date.now());
            setStream(stream)
            setRecording(recorder);
            recorder.startRecording()
        } catch (error) {
            console.error("Failed to start recording: ", error)
        }
    }

    const uploadRecording = async (audioBlob) => {
        console.log("uploadRecording")
        // OMG, How hard this can be? Literally spent half a day setting up the full shabbang
        // Made me HATE CORS
        // Browser restrictions: Modern web browsers enforce CORS policy by default
        // and don't provide an option to disable it. GREAT, especially when AWS API Gateway does not allow to ALLOW it.

        // First, get the presigned URL from your Lambda function
        const headers = {};
        if (accountId) {
            headers['X-Account-Id'] = accountId;
        }
        const presigned_response = await fetch(PRESIGNED_URL, {
            method: 'GET',
            headers: headers,
        });
        const data = await presigned_response.json(); // parse response to JSON

        // set states
        setExistingEmail(data.email);
        setCollectEmail(!Boolean(data.email))
        setAccountId(data.account_id);

        // for presignedUrl use the same way you have used
        const presignedUrl = data.presigned_url;
        // Then, upload the audio file to S3 using the presigned URL
        const response = await Promise.race([
            fetch(presignedUrl, {
                method: 'PUT',
                body: audioBlob,
                headers: {
                    // NOTE: This needs to remain same as the lambda in the backend
                    'Content-Type': 'audio/webm'
                }
            }),
            new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), UPLOAD_TIMEOUT)),
        ]);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        return response;
    }

    const stopRecording = async () => {
        console.log(`stopRecording for ${recording}`)
        if (!recording) {
            return;
        }

        recording.stopRecording(async () => {
            fullyReleaseMike()

            const audioBlob = recording.getBlob();
            const audioURL = URL.createObjectURL(audioBlob);

            console.log(`check recording long enough ${recordingElapsedTime} >= ${MIN_DURATION}`);
            if (recordingElapsedTime < MIN_DURATION) {
                setRecorderState(RecorderState.TOO_SHORT)

                setTimeout(() => {
                    console.log('recording short auto-refresh');
                    setRecorderState(RecorderState.WELCOME);
                }, SHORT_RECORDING_TIMEOUT);

                return;
            }

            setAudioURL(audioURL);
            setRecorderState(RecorderState.UPLOADING)

            try {
                await uploadRecording(audioBlob);
                setRecorderState(RecorderState.SUCCESS)
            } catch (error) {
                console.error("Failed to upload recording: ", error);
                setRecorderState(RecorderState.FAILURE)
                setFailureMessage(error)
            } finally {
                // Reset all the states from startRecording
                setStream(null)
                setRecording(null);
            }
        });
    };

// In the main component...
    return (
        <div>
            <div className="flex flex-col items-center">
                {recorderState === RecorderState.WELCOME && <WelcomeState onStartRecording={startRecording}/>}
                {recorderState === RecorderState.RECORDING &&
                    <RecordingState onStopRecording={stopRecording} elapsedTime={recordingElapsedTime}/>}
                {recorderState === RecorderState.UPLOADING && <UploadingState/>}
                {recorderState === RecorderState.SUCCESS &&
                    <SuccessState collectEmail={collectEmail} existingEmail={existingEmail} accountId={accountId}/>}
                {recorderState === RecorderState.TOO_SHORT && <TooShortState/>}
                {recorderState === RecorderState.FAILURE &&
                    <FailureState audioURL={audioURL} failureMessage={failureMessage}/>}
            </div>
        </div>
    );
}
