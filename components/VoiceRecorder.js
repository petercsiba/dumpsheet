// TODO(P1, browser-compatibility): Mobile Safari displays a weirdly small <audio> tag
import {useEffect, useRef, useState} from 'react'
import RecordRTC from 'recordrtc'
import Image from 'next/image'
// https://uxwing.com/stop-button-red-icon/
import MicrophoneIcon from '../public/images/icons/microphone-button-green-icon.svg'
import MicrophoneIconHover from '../public/images/icons/microphone-button-green-hover-icon.png'
import StopIcon from '../public/images/icons/stop-button-red-icon.svg'
import CollectEmailProcessingInfo from "@/components/CollectEmailProcessingInfo";
import ProgressBar from "@/components/ProgressBar";
import {useAccount} from "@/contexts/AccountContext";

const PRESIGNED_URL = 'https://api.voxana.ai/upload/voice';
const UPLOAD_TIMEOUT = 30000;
const MIN_DURATION = Number(process.env.NEXT_PUBLIC_VOICE_RECORDER_MIN_DURATION_SECONDS) || 10;
const SHORT_RECORDING_TIMEOUT = 7000;

const RecorderState = {
    // For handholding demo
    DEMO_SELECT_PERSONA: 'demo_select_persona',
    DEMO_PLAY_PERSONA: 'demo_play_persona',
    // For real-use
    WELCOME: 'welcome',
    RECORDING: 'recording',
    UPLOADING: 'uploading',
    SUCCESS: 'success',
    FAILURE: 'failure',
    TOO_SHORT: 'too_short',
    DEBUG: 'debug'
};

const formatDuration = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
};

const HeadingText = ({text}) => (
    <div className="text-center font-semibold text-black text-2xl tracking-normal leading-normal pb-5">
        {text}
    </div>
)

const WelcomeState = ({onStartRecording}) => {
    const [imageSrc, setImageSrc] = useState(MicrophoneIcon);

    return (
        <>
            <HeadingText text={"Tell Me About Your Meeting"}/>
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
                            width={80}
                            height={80}
                        />
                    </div>
                    <div>
                        Start
                    </div>
                </button>
            </div>
            <ProgressBar currentStep={0}/>
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
                        width={60}
                        height={60}
                    />
                </div>
                <div>
                    Stop
                </div>
            </button>
            <div className="mt-2">
                <p>{formatDuration(elapsedTime)}</p>
            </div>
            <ProgressBar currentStep={1}/>
        </div>
    </>
);

const UploadingState = () => (
    <>
        <HeadingText text={"Uploading ..."}/>
        <ProgressBar currentStep={2}/>
    </>
);
const SuccessState = ({ collectEmail, existingEmail, accountId, onTryAgain }) => {
    const [showButton, setShowButton] = useState(false);
    const [step, setStep] = useState(2);
    const [headingText, setHeadingText] = useState("Upload was successful!");

    const handleSuccess = () => {
        setHeadingText(isDemo() ? "Demo finished!" : "Next Steps")
        setShowButton(isDemo());
        setStep(3);
        clearDemo()  // So in next success, this won't happen.
        console.log(`CollectEmailProcessingInfo success setShowButton: ${showButton}`)
    };

    return (
        <>
            <HeadingText text={headingText} />
            <CollectEmailProcessingInfo
                collectEmail={collectEmail}
                existingEmail={existingEmail}
                accountId={accountId}
                onSuccess={handleSuccess}
            />
            {showButton && <div className="pt-8"><SelectButton label={"Now Try Yourself!"} onClick={onTryAgain}/></div>}
            {!showButton && <ProgressBar currentStep={step} />}
        </>
    );
}


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


class Persona {
    constructor(displayName, webmUrl, transcript) {
        this.displayName = displayName;
        this.webmUrl = webmUrl;
        this.transcript = transcript;
    }
}

const personaMap = {
    'A': new Persona(
        'Arnold Schwarzenegger',
        '/sample-voice-memos/arnold-test.webm',
        'If you\'ve seen my movies, you might think this is about terminating threats. Today, it\'s about protecting John Connor, the future leader of human resistance. His needs are survival and skill development. My job? Keep him safe and train him in combat. Because the fate of humanity rests on his shoulders. It\'s not just "Hasta la vista, baby"—it\'s shaping the future, one mission at a time.'
    ),
    'B': new Persona(
        'Taylor Swift',
        '/sample-voice-memos/arnold-test.webm',
        'Taylor also penned a lengthy prologue for 1989 (Taylor\'s Version), recalling how she "swore off hanging out with guys" to avoid the negativity surrounding her dating life while making the album in 2014.\n' +
        '\n' +
        '"There was so much that I didn\'t know then, and looking back I see what a good thing that was," she wrote in part. "It turns out that the cocktail of naïveté, hunger for adventure and freedom can lead to some nasty hangovers, metaphorically speaking. Of course everyone had something to say, but they always will."\n' +
        '\n' +
        'And when it comes to her five never-before-heard vault tracks, read on for the full breakdown of the references and Easter Eggs:'
    ),
    'C': new Persona(
        'Khary Payton',
        '/sample-voice-memos/arnold-test.webm',
        'Dont get me wrong, I love Khary Payton and his work. However, it kind of annoys me that he plays every black male character. Its like they think all black men sound the same. Im sure thats not what actually think, but thats the impression that it exuding.\n' +
        '\n' +
        'Aquaman (Aqualad) Black Lightning Dr. Stone Black Manta Maybe Static too\n' +
        '\n' +
        'Also, I think its ironic that the only other black character that he doesnt play on yj is Victor Stone/Cyborg. And he plays Cyborg on Teen Titans..'
    )
};


const SelectButton = ({label, onClick}) => {
    return (
        <button
            onClick={onClick}
            className="flex items-center justify-center w-60 h-12 text-black border border-black rounded-full font-semibold text-lg tracking-tighter bg-white hover:bg-gray-100"
        >
            {label}
        </button>
    );
};


const SelectPersonaState = ({onSelectPersona}) => {
    return (
        <>
            <HeadingText text={"Select a Persona"}/>
            <div className="flex flex-col items-center text-center">
                <p>
                    To showcase Voxana for you, <br/>
                    pick one person to do a voice recording for you!
                </p>
                <div className="pt-4"><SelectButton onClick={() => onSelectPersona('A')}
                                                    label={"Arnold Schwarzenegger"}/></div>
                <div className="pt-4"><SelectButton onClick={() => onSelectPersona('B')} label={"Taylor Swift"}/></div>
                <div className="pt-4"><SelectButton onClick={() => onSelectPersona('C')} label={"Khary Payton"}/></div>
            </div>
        </>
    );
};

const PlayPersonaState = ({onPlaybackComplete, currentPersona}) => {
    const audioRef = useRef(null);
    const [progress, setProgress] = useState(0);

    useEffect(() => {
        // Initialize the audio element and play
        const audioElement = audioRef.current;
        audioElement.addEventListener('error', (e) => {
            console.error("Audio Error:", e);
        });

        const audioURL = `${currentPersona.webmUrl}`
        console.log(`set audioElement.src to ${audioURL}`)
        audioElement.src = audioURL;
        // TODO(P1): This leads to Playback error: DOMException:
        //  The fetching process for the media resource was aborted by the user agent at the user's request.
        // BUT the audio still plays so :shrug:
        // https://chat.openai.com/share/62db5975-b570-4e55-8613-7370b403bc75
        audioElement.play().catch(error => {
            console.error("Playback error:", error);
        });

        const handleTimeUpdate = () => {
            setProgress((audioElement.currentTime / audioElement.duration) * 100);
        };

        // When the audio ends
        const handleEnded = () => {
            onPlaybackComplete();
        };

        audioElement.addEventListener('timeupdate', handleTimeUpdate);
        audioElement.addEventListener('ended', handleEnded);

        return () => {
            audioElement.removeEventListener('timeupdate', handleTimeUpdate);
            audioElement.removeEventListener('ended', handleEnded);
        };
    }, [onPlaybackComplete, currentPersona]);

    return (
        <>
            <HeadingText text={`Playing Persona ${currentPersona.displayName}...`}/>
            <div className="flex flex-col items-center">
                <audio ref={audioRef}/>
                <div>
                    <div style={{width: `${progress}%`}} className="progress-bar"></div>
                </div>
                <h2>Transcript of recording</h2>
                <p>{currentPersona.transcript}</p>
                <ProgressBar currentStep={1}/>
            </div>
        </>
    );
};


const isDemo = () => {
    return window.location.pathname === '/demo' || new URLSearchParams(window.location.search).get('demo') === 'true';
}

const clearDemo = () => {
    const newUrl = new URL(window.location.href);
    newUrl.searchParams.delete('demo');
    window.history.replaceState({}, '', newUrl.toString());
}

export default function VoiceRecorder() {
    // Main state
    const isFirstTimeUser = isDemo()
    const [recorderState, setRecorderState] = useState(isFirstTimeUser ? RecorderState.DEMO_SELECT_PERSONA : RecorderState.WELCOME);

    // Media related
    const [stream, setStream] = useState(null);
    const [recording, setRecording] = useState(null);
    const [audioURL, setAudioURL] = useState(null);
    const [recordingStartTime, setRecordingStartTime] = useState(null);
    const [recordingElapsedTime, setRecordingElapsedTime] = useState(0);

    // User info related
    const [collectEmail, setCollectEmail] = useState(null);
    const [existingEmail, setExistingEmail] = useState(null);
    const {accountId, setAccountId} = useAccount();

    // Demo related
    const [currentPersona, setCurrentPersona] = useState(null);

    // When things go wrong
    const [failureMessage, setFailureMessage] = useState(null);


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

    const uploadRecordingWrapper = async (audioBlob) => {
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
    };

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
            // In case uploading fails, they can download it from this URL.
            setAudioURL(URL.createObjectURL(audioBlob));

            console.log(`check recording long enough ${recordingElapsedTime} >= ${MIN_DURATION}`);
            if (recordingElapsedTime < MIN_DURATION) {
                setRecorderState(RecorderState.TOO_SHORT)

                setTimeout(() => {
                    console.log('recording short auto-refresh');
                    setRecorderState(RecorderState.WELCOME);
                }, SHORT_RECORDING_TIMEOUT);

                return;
            }

            return uploadRecordingWrapper(audioBlob)
        });
    };

    // Demo related
    const selectPersona = (personaId) => {
        console.log(`selectPersona ${personaId}`)
        const currentPersona = personaMap[personaId]; // Look up details based on id
        setCurrentPersona(currentPersona);
        setRecorderState(RecorderState.DEMO_PLAY_PERSONA);
    }

    const moveToUploading = async () => {
        console.log(`moveToUploading for ${currentPersona}`)
        const response = await fetch(currentPersona.webmUrl);
        if (!response.ok) {
            throw new Error(`Failed to download example persona recording from ${currentPersona.webmUrl}`);
        }
        const audioBlob = await response.blob()
        return uploadRecordingWrapper(audioBlob)
    }


// In the main component...
    return (
        <div>
            <div className="flex flex-col items-center">
                {recorderState === RecorderState.DEMO_SELECT_PERSONA &&
                    <SelectPersonaState onSelectPersona={selectPersona}/>}
                {recorderState === RecorderState.DEMO_PLAY_PERSONA &&
                    <PlayPersonaState onPlaybackComplete={moveToUploading} currentPersona={currentPersona}/>}

                {recorderState === RecorderState.WELCOME && <WelcomeState onStartRecording={startRecording}/>}
                {recorderState === RecorderState.RECORDING &&
                    <RecordingState onStopRecording={stopRecording} elapsedTime={recordingElapsedTime}/>}
                {recorderState === RecorderState.UPLOADING && <UploadingState/>}
                {recorderState === RecorderState.SUCCESS &&
                    <SuccessState collectEmail={collectEmail} existingEmail={existingEmail} accountId={accountId}
                                  onTryAgain={() => setRecorderState(RecorderState.WELCOME)}/>}
                {recorderState === RecorderState.TOO_SHORT && <TooShortState/>}
                {recorderState === RecorderState.FAILURE &&
                    <FailureState audioURL={audioURL} failureMessage={failureMessage}/>}
                {recorderState === RecorderState.DEBUG &&
                    <SuccessState collectEmail={true} existingEmail={existingEmail} accountId={accountId}
                                  onTryAgain={() => setRecorderState(RecorderState.WELCOME)}/>}
            </div>
        </div>
    );
}
