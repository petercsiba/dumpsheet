// TODO(P1, devx): Extract common components to be re-used
// TODO(P1, browser-compatibility): Mobile Safari displays a weirdly small <audio> tag
import React, {useEffect, useRef, useState} from 'react'
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
    WELCOME_PRIVATE_BETA: 'welcome_private_beta',
    LETS_RECORD: 'lets_record',
    RECORDING: 'recording',
    UPLOADING: 'uploading',
    REGISTER_EMAIL: 'register_email',
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


const WelcomePrivateBetaState = ({onSuccess}) => {
    const [codes, setCodes] = useState(['', '', '', '']);
    const [errorMessage, setErrorMessage] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const inputRefs = [useRef(null), useRef(null), useRef(null), useRef(null)];

    useEffect(() => {
        if (inputRefs[0].current) {
            inputRefs[0].current.focus();
        }
    }, []);

    const handleInputChange = (e, index) => {
        const value = e.target.value;

        if (!isNaN(value) && value.length <= 1) {
            const newCodes = [...codes];
            newCodes[index] = value;
            setCodes(newCodes);

            if (index < 3 && value !== '') {
                inputRefs[index + 1].current.focus();
            }

            const fullCode = newCodes.join('');
            if (fullCode.length === 4) {
                if (fullCode === '1876') {
                    setSuccessMessage("Correct - thanks! (Redirecting ...)");
                    setTimeout(onSuccess, 1000);  // 1 second delay
                } else {
                    setErrorMessage("Wrong code, please contact support@voxana.ai");
                }
            }
        }
    };

    return (
        <>
            <HeadingText text={"Welcome to Voxana!"}/>
            { /* <p className="font-bold">Your voice-first personal networking CRM</p> */}
            <p className="font-bold">We are in private beta, please provide a 4 digit code:</p>
            <div className="pt-4" style={{display: 'flex', justifyContent: 'space-between', maxWidth: '200px'}}>
                {codes.map((code, index) => (
                    <input
                        key={index}
                        type="text"
                        value={code}
                        ref={inputRefs[index]}
                        onChange={(e) => handleInputChange(e, index)}
                        maxLength={1}
                        style={{
                            width: '40px',
                            textAlign: 'center',
                            border: '1px solid #000',  // border style
                            borderRadius: '4px',  // border-radius for slight rounding of corners
                            margin: '0 2px',  // small margin for spacing between input boxes
                            padding: '5px'
                        }}
                    />
                ))}
            </div>
            {errorMessage && <p className="pt-8 text-red-500">{errorMessage}</p>}
            {successMessage && <p className="pt-8 text-green-700 font-bold">{successMessage}</p>}
        </>
    );
};


const LetsRecordState = ({onStartRecording}) => {
    const [imageSrc, setImageSrc] = useState(MicrophoneIcon);

    return (
        <>
            <HeadingText text={"Tell Me About Your Meeting"}/>
            <p className="pb-8">Mention people, facts or any action items</p>
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
        <HeadingText text={"Uploading Your Voice Memo ..."}/>
        <div className="flex flex-col items-center justify-center">
            Your recording is being processed. Please wait for a moment.
        </div>
        <ProgressBar currentStep={2}/>
    </>
);

const RegisterEmailState = ({accountId, onRegistrationSuccess}) => {
    return (
        <>
            <HeadingText text={"Almost There!"}/>
            <CollectEmailProcessingInfo accountId={accountId} onRegistrationSuccess={onRegistrationSuccess}/>
            <ProgressBar currentStep={2}/>
        </>
    );
}

const SuccessState = ({comesFromDemo, userEmailAddress, onRecordAgain}) => {
    return (
        <>
            <HeadingText text={comesFromDemo ? "Demo Complete!" : "Congrats, All Done Here!"}/>
            <div className="pl-4">
                <span className="font-bold text-base">Now, you</span>
                <ul className="list-disc list-inside text-">
                    <li className="mt-1">Go check email(s) from assistant@voxana.ai
                        <br /> &nbsp; &nbsp; (should arrive within a few minutes)
                    </li>
                    <li className="mt-1">Send responses / follow ups to your contacts</li>
                    <li className="mt-1">Fill in your Voxana spreadsheet</li>
                </ul>
            </div>

            {comesFromDemo &&
                <div className="pt-8"><SelectButton label={"Now Try For Yourself!"} onClick={onRecordAgain}/></div>}

            {!comesFromDemo && (
                <>
                    <ProgressBar currentStep={3}/>
                    <div className="h-0.5 bg-gray-300 my-4 justify-items-end" style={{ width: '92%' }}></div> {/* Horizontal line */}
                    {/*<div className="pt-8 pb-2"><b>More encounters on your mind?</b></div>*/}
                    {/*<div><SelectButton label={"Record Another One"} onClick={onRecordAgain}/></div>*/}
                    <div className="flex justify-end">
                        <button
                            onClick={onRecordAgain}
                            className="px-4 py-1 mr-0 text-black border border-black rounded-full font-semibold text-base tracking-tighter bg-white hover:bg-gray-300"
                        >
                            Record Another One
                        </button>
                    </div>
                </>
            )}
        </>
    )
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
    constructor(displayName, webmUrl, mp3Url, recordingTitle, transcript) {
        this.displayName = displayName;
        // The code seems to try to play a .webm audio format, which Firefox supports but Safari doesn't.
        // Safari lacks support for the WebM container and its associated VP8 and VP9 video codecs.
        this.mp3Url = mp3Url;
        this.webmUrl = webmUrl;
        this.recordingTitle = recordingTitle;
        this.transcript = transcript;
    }
}

const personaMap = {
    'A': new Persona(
        'Arnold Schwarzenegger',
        '/sample-voice-memos/arnold-test.webm',
        '/sample-voice-memos/arnold-test.mp3',
        'Terminators mission John Connor',
        'If you\'ve seen my movies, you might think this is about terminating you. Today, it\'s about protecting John Connor, the future leader of human resistance. His needs are survival and skill development. My job? Keep him safe and train him in combat. Because the fate of humanity rests on his shoulders. It\'s not just "Hasta la vista, baby"—it\'s shaping the future, one mission at a time.'
    ),
    'B': new Persona(
        'Taylor Swift',
        '/sample-voice-memos/taylor-swift-and-travis.webm',
        '/sample-voice-memos/taylor-swift-and-travis.mp3',
        'Taylor meets Travis Kelce',
        'So I finish this gig at Arrowhead Stadium, home of the Chiefs, and what do I find but a friendship bracelet from tight end Travis Kelce himself. He couldn\'t chat at the show — vocal rest and all. Later on, there\'s Travis in New York, knee injury and all, trying to downplay the whole \'I almost missed the season\' thing. We ended up joking about turning his on-field audibles into song lyrics. Who knew NFL plays could sound so poetic?'
    ),
    // 'C': new Persona(
    //     'Khary Payton',
    //     '/sample-voice-memos/arnold-test.webm',
    //     '/sample-voice-memos/arnold-test.mp3',
    //     'Khary jams with Tara Strong',
    //     'I was at this voice-over gig, and out of nowhere, Tara Strong starts doing her Raven impression, saying \'Azarath Metrion Zinthos\' in the booth. And I just couldn’t resist, so I jump in with my Cyborg \'Booyah!\' It\'s all fun until I knock over a stack of scripts, and we\'re scrambling like in a cartoon, scripts flying everywhere. Tara\'s laughing so hard, she can barely speak. Just another day saving the world, right?'
    // )
};


const SelectButton = ({label, onClick}) => {
    return (
        <button
            onClick={onClick}
            className="flex items-center justify-center w-60 h-12 text-black border border-black rounded-full font-semibold text-lg tracking-tighter bg-white hover:bg-gray-300"
        >
            {label}
        </button>
    );
};


const SelectPersonaState = ({onSelectPersona}) => {
    return (
        <>
            <HeadingText text={"Demo: How We Simplify Your Data Entry"}/>
            <div className="flex flex-col items-center text-center">
                <p className="text-lg pb-4">
                    <b>Pick a narrator</b> to walk you through Voxana's seamless process: <br/>
                </p>
                <div className="pt-4"><SelectButton onClick={() => onSelectPersona('A')}
                                                    label={"Arnold Schwarzenegger"}/></div>
                <div className="pt-4"><SelectButton onClick={() => onSelectPersona('B')} label={"Taylor Swift"}/></div>
                { /* <div className="pt-4"><SelectButton onClick={() => onSelectPersona('C')} label={"Khary Payton"}/></div> */}
            </div>
        </>
    );
};

function isSafari() {
    return /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
}

const ProgressBarTo100 = ({progressPercent}) => {
    return (
        <div className="relative w-full h-6 bg-white border-2 border-black">
            <div
                className="absolute w-full flex justify-center items-center h-full top-0 left-0"
                aria-hidden="true"
            >
                <span className="text-sm font-bold text-black">{progress}%</span>
            </div>
            <div
                className="h-6 bg-green-300"
                style={{width: `${progress}%`}}
                role="progressbar"
                aria-valuenow={progress}
                aria-valuemin="0"
                aria-valuemax="100"
            />
        </div>
    );
};

const PlayPersonaState = ({onPlaybackComplete, currentPersona}) => {
    const audioRef = useRef(null);
    const [progressPercent, setProgressPercent] = useState(0);

    useEffect(() => {
        // Initialize the audio element and play
        const audioElement = audioRef.current;
        audioElement.addEventListener('error', (e) => {
            console.error("Audio Error:", e);
        });

        if (isSafari()) {
            console.log("isSafari true")
            audioElement.src = currentPersona.mp3Url;
        } else {
            audioElement.src = currentPersona.webmUrl;
        }
        console.log(`set audioElement.src to ${audioElement.src}`);

        audioElement.play()
            .catch(error => {
                // TODO: We might be able to remove this
                // if (error.name === 'NotSupportedError') {
                audioElement.src = currentPersona.mp3Url;
                console.log(`WebM format not supported ${error}, trying MP3: ${audioElement.src}`);
                // TODO(P1): This sometimes leads to Playback error: DOMException:
                //  The fetching process for the media resource was aborted by the user agent at the user's request.
                // BUT the audio still plays so :shrug:
                // https://chat.openai.com/share/62db5975-b570-4e55-8613-7370b403bc75
                return audioElement.play();  // Play the MP3 version
                // } else {
                //    throw error;  // If it's another error, re-throw it
                // }
            })
            .catch(error => {
                console.error("MP3 Playback error:", error);
            });
        audioElement.play().catch(error => {
            console.error("WebM Playback error:", error);
        });

        const handleTimeUpdate = () => {
            const progress = Math.round((audioElement.currentTime / audioElement.duration) * 100);
            setProgressPercent(progress);
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
            <HeadingText text={`Demo Recording of a Voice Note`}/>
            <div className="flex flex-col items-center">
                <p className="text-lg pb-4"><b>Now playing:</b> {currentPersona.recordingTitle}</p>
                <p className="text-lg pb-4">Recording Transcript:</p>
                <p className="font-mono pb-4">{currentPersona.transcript}</p>
                <audio ref={audioRef}/>
                <ProgressBarTo100 progressPercent={progressPercent}/>
            </div>
            <ProgressBar currentStep={1}/>
        </>
    );
};


const isDebug = () => {
    return new URLSearchParams(window.location.search).get('debug') === 'true';
}

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
    const [recorderState, setRecorderState] = useState(isDebug() ? RecorderState.DEBUG : isFirstTimeUser ? RecorderState.DEMO_SELECT_PERSONA : RecorderState.LETS_RECORD);

    // Media related
    const [stream, setStream] = useState(null);
    const [recording, setRecording] = useState(null);
    const [audioURL, setAudioURL] = useState(null);
    const [recordingStartTime, setRecordingStartTime] = useState(null);
    const [recordingElapsedTime, setRecordingElapsedTime] = useState(0);

    // Login info related
    const [registeredEmail, setRegisteredEmail] = useState(null);
    const {accountId, setAccountId} = useAccount();

    // Demo related
    const [currentPersona, setCurrentPersona] = useState(null);

    // When things go wrong
    const [failureMessage, setFailureMessage] = useState(null);


    const doCollectEmail = () => {
        return registeredEmail === null || `${registeredEmail}`.length < 6  // a@a.ai
    }

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

    const doUploadAndProceedNext = async (audioBlob) => {
        setRecorderState(RecorderState.UPLOADING)

        try {
            await uploadRecording(audioBlob);
            const nextState = doCollectEmail() ? RecorderState.REGISTER_EMAIL : RecorderState.SUCCESS
            console.log(`uploading finished, next state is ${nextState}`)
            setRecorderState(nextState)
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
        // TLDR: Make SURE that OPTIONS also respond with CORS HEADERS (and know these are cached heavily).

        // First, get the presigned URL from your Lambda function
        const headers = {};
        // if (accountId) {
        //     headers['X-Account-Id'] = accountId;
        // }
        const presigned_response = await fetch(PRESIGNED_URL, {
            method: 'GET',
            headers: headers,
        });
        const data = await presigned_response.json(); // parse response to JSON
        setRegisteredEmail(data.email);
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
                    setRecorderState(RecorderState.LETS_RECORD);
                }, SHORT_RECORDING_TIMEOUT);

                return;
            }

            return doUploadAndProceedNext(audioBlob)
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
        return doUploadAndProceedNext(audioBlob)
    }

    const onRegistrationSuccess = (emailAddress) => {
        console.log(`onRegistrationSuccess ${emailAddress}`)
        setRegisteredEmail(emailAddress)
        setRecorderState(RecorderState.SUCCESS)
    }

    const onRecordAgain = () => {
        console.log("onRecordAgain")
        clearDemo()
        setRecorderState(RecorderState.LETS_RECORD)
    }

// In the main component...
    return (
        <div>
            <div className="flex flex-col items-center">
                {recorderState === RecorderState.DEMO_SELECT_PERSONA &&
                    <SelectPersonaState onSelectPersona={selectPersona}/>}
                {recorderState === RecorderState.DEMO_PLAY_PERSONA &&
                    <PlayPersonaState onPlaybackComplete={moveToUploading} currentPersona={currentPersona}/>}

                {recorderState === RecorderState.WELCOME_PRIVATE_BETA &&
                    <WelcomePrivateBetaState onSuccess={() => setRecorderState(RecorderState.LETS_RECORD)}/>}
                {recorderState === RecorderState.LETS_RECORD && <LetsRecordState onStartRecording={startRecording}/>}
                {recorderState === RecorderState.RECORDING &&
                    <RecordingState onStopRecording={stopRecording} elapsedTime={recordingElapsedTime}/>}
                {recorderState === RecorderState.UPLOADING && <UploadingState/>}
                {recorderState === RecorderState.REGISTER_EMAIL &&
                    <RegisterEmailState accountId={accountId} onRegistrationSuccess={onRegistrationSuccess}/>
                }
                {recorderState === RecorderState.SUCCESS &&
                    <SuccessState comesFromDemo={isDemo()} userEmailAddress={registeredEmail}
                                  onRecordAgain={onRecordAgain}/>}
                {recorderState === RecorderState.TOO_SHORT && <TooShortState/>}
                {recorderState === RecorderState.FAILURE &&
                    <FailureState audioURL={audioURL} failureMessage={failureMessage}/>}

                {recorderState === RecorderState.DEBUG &&
                    <SuccessState comesFromDemo={isDemo()} userEmailAddress={registeredEmail}
                                  onRecordAgain={onRecordAgain}/>}
            </div>
        </div>
    );
}
