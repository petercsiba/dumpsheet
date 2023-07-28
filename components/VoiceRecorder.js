// TODO(P1, browser-compatibility): Mobile Safari displays a weirdly small <audio> tag
import { useEffect, useState } from 'react'
import RecordRTC from 'recordrtc'
import Image from 'next/image'
import MicrophoneIcon from '../public/images/icons/microphone-icon.svg'
import StopIcon from '../public/images/icons/stop-icon.svg'
import CollectEmailProcessingInfo from "@/components/CollectEmailProcessingInfo";

const PRESIGNED_URL = 'https://api.voxana.ai/upload/voice';
const UPLOAD_TIMEOUT = 20000;
const MIN_DURATION = Number(process.env.NEXT_PUBLIC_VOICE_RECORDER_MIN_DURATION_SECONDS) || 10;
const SHORT_RECORDING_TIMEOUT = 2500;


const formatDuration = (seconds) => {
	const minutes = Math.floor(seconds / 60);
	const remainingSeconds = Math.floor(seconds % 60);
	return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
};

const StopRecordingButton = () => (
	<div className="bg-white-500 p-2 inline-block">
		<Image
			priority
			src={StopIcon}
			alt="Stop and upload recording"
			width={50}
			height={50}
		/>
	</div>
);

const StartRecordingButton = () => (
	<div className="inline-block">
		<Image
			priority
			src={MicrophoneIcon}
			alt="Start your voice recording"
			width={100}
			height={100}
		/>
	</div>
);

export default function VoiceRecorder() {
	// TODO(P1, devx): We should split this function up to the actual voice recorder and the subsequent screens logic.
	const [stream, setStream] = useState(null);
	const [recording, setRecording] = useState(null)
	const [audioURL, setAudioURL] = useState(null)
	const [uploadStatus, setUploadStatus] = useState(null);
	const [uploadSuccess, setUploadSuccess] = useState(null);
	const [recordingStartTime, setRecordingStartTime] = useState(null);
	const [recordingElapsedTime, setRecordingElapsedTime] = useState(0);
	const [duration, setDuration] = useState(null);
	const [collectEmail, setCollectEmail] = useState(null);
	const [existingEmail, setExistingEmail] = useState(null);
	const [accountId, setAccountId] = useState(null);
	const [processing, setProcessing] = useState(null)


	useEffect(() => {
		let interval = null;

		if (recording) {
			interval = setInterval(() => {
				const secondsElapsed = (Date.now() - recordingStartTime) / 1000;
				setRecordingElapsedTime(secondsElapsed);
				setDuration(secondsElapsed)
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
		try {
			const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
			const recorder = new RecordRTC(stream, {
				type: 'audio',
				mimeType: 'audio/webm'
			})

			setStream(stream)
			setRecording(recorder)
			setRecordingStartTime(Date.now());
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
		const presigned_response = await fetch(PRESIGNED_URL, { method: 'GET' });
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
				setUploadStatus(`Recording needs to be longer than ${MIN_DURATION} seconds, please try again.`);

				setTimeout(() => {
					console.log('recording short auto-refresh');
					setUploadStatus(null);
				}, SHORT_RECORDING_TIMEOUT);

				return;
			}

			setAudioURL(audioURL);
			setUploadStatus('Uploading...');

			try {
				await uploadRecording(audioBlob);

				setUploadSuccess(true);
				setUploadStatus('Uploaded successfully!');
				setProcessing(true)
			} catch (error) {
				console.error("Failed to upload recording: ", error);
				setUploadSuccess(false)

				if (error.message === 'Timeout') {
					setUploadStatus('Your request timed out. Please check your internet connection.');
				} else {
					setUploadStatus(`Failed to upload the recording. Please try again or send this to support@voxana.ai: ${error}`);
				}
			} finally {
				setRecording(null);
			}
		});
	};

	const AudioPlayer = ({ audioURL, duration }) => (
		<div>
			<audio className="pl-8 pr-8" src={audioURL} controls />
			<p className="flex justify-center">Duration: {formatDuration(duration)}</p>
		</div>
	);

	const AlternativeUpload = ({ audioURL }) => {
		const fileName = `voxana-audio-recording-${Date.now()}.webm`;

		return (
			<div className="bg-white-500 p-2 inline-block">
				<p className="py-2">Alternatively, download and upload manually.</p>
				<div className="flex justify-center">
					<a href={audioURL} download={fileName}>Download</a>
				</div>
			</div>
		);
	};

// In the main component...
	return (
		<div className="flex flex-col items-center">
			{ /* audioURL && <AudioPlayer audioURL={audioURL} duration={duration} /> <br/> */}
			{!Boolean(uploadStatus) && <button
				className="btn-white p-0"
				onClick={recording ? stopRecording : startRecording}
				disabled={Boolean(uploadStatus)}
			>
				{ recording
						? <StopRecordingButton />
						: <StartRecordingButton />
				}
			</button>
			}
			{recording && <p>{formatDuration(recordingElapsedTime)}</p>}

			{Boolean(uploadStatus) && <p>{uploadStatus}</p>}

			{uploadSuccess === false && <AlternativeUpload audioURL={audioURL} />}

			{
				processing === true && <CollectEmailProcessingInfo collectEmail={collectEmail} existingEmail={existingEmail} accountId={accountId} />
			}
		</div>
	);
}
