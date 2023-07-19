import { useEffect, useState } from 'react'
import RecordRTC from 'recordrtc'
import Image from 'next/image'
import MicrophoneIcon from '../public/images/icons/microphone-icon.svg'
import StopIcon from '../public/images/icons/stop-icon.svg'

const UPLOAD_URL = 'http://api.voxana.ai/uploads/';
const UPLOAD_TIMEOUT = 20000;
const MIN_DURATION = Number(process.env.VOICE_RECORDER_MIN_DURATION_SECONDS) || 10;
const SHORT_RECORDING_TIMEOUT = 2500;

const formatDuration = (seconds) => {
	const minutes = Math.floor(seconds / 60);
	const remainingSeconds = Math.floor(seconds % 60);
	return `${minutes}m : ${remainingSeconds}s`;
};

export default function VoiceRecorder() {
	const [recording, setRecording] = useState(null)
	const [audioURL, setAudioURL] = useState(null)
	const [uploadStatus, setUploadStatus] = useState(null);
	const [uploadSuccess, setUploadSuccess] = useState(null);
	const [recordingStartTime, setRecordingStartTime] = useState(null);
	const [recordingElapsedTime, setRecordingElapsedTime] = useState(0);
	const [duration, setDuration] = useState(null);

	// `duration` might be slightly redundant with recordingElapsedTime, but in theory more precise
	// Leads to Infinity : NaN
	// useEffect(() => {
	// 	const audio = new Audio(audioURL);
	//
	// 	// Once the metadata has been loaded, get the duration
	// 	audio.onloadedmetadata = function() {
	// 		setDuration(audio.duration);
	// 	};
	// }, [audioURL]); // dependency array

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

	const startRecording = async () => {
		if (typeof window === 'undefined') {
			console.error('Recording is not supported on the server.')
			return
		}
		try {
			const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
			const recorder = new RecordRTC(stream, {
				type: 'audio',
				mimeType: 'audio/webm'
			})

			setRecordingStartTime(Date.now());
			setRecording(recorder)
			recorder.startRecording()
		} catch (error) {
			console.error("Failed to start recording: ", error)
		}
	}

	const uploadRecording = async (audioBlob) => {
		const formData = new FormData();
		formData.append('audio', audioBlob);

		const response = await Promise.race([
			fetch(UPLOAD_URL, {
				method: 'POST',
				body: formData
			}),
			new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), UPLOAD_TIMEOUT))
		]);

		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}

		return response;
	}

	const stopRecording = async () => {
		if (!recording) {
			return;
		}

		recording.stopRecording(async () => {
			const audioBlob = recording.getBlob();
			const audioURL = URL.createObjectURL(audioBlob);

			console.log(`check recording long enough ${recordingElapsedTime} >= ${MIN_DURATION}`);

			if (recordingElapsedTime < MIN_DURATION) {
				setUploadStatus(`Recording needs to be longer than ${MIN_DURATION} seconds, please try again.`);

				setTimeout(() => {
					console.log('recording short auto-refresh');
					setRecording(null);  // should also reset the elapsedTime
					setUploadStatus(null);
				}, SHORT_RECORDING_TIMEOUT);

				return;
			}

			setAudioURL(audioURL);
			setUploadStatus('Uploading...');

			try {
				const response = await uploadRecording(audioBlob);

				setUploadSuccess(true);
				setUploadStatus('Uploaded successfully!');
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

	const RecordingButton = ({ recordingElapsedTime }) => (
		<div>
			<div className="bg-white-500 p-2 inline-block">
				<Image
					priority
					src={StopIcon}
					alt="Stop and upload recording"
					width={50}
					height={50}
				/>
			</div>
			<p>{formatDuration(recordingElapsedTime)}</p>
		</div>
	);

	const StartRecordingButton = () => (
		<div className="bg-gray-200 p-2 inline-block rounded-full border-2 border-black">
			<Image
				priority
				src={MicrophoneIcon}
				alt="Start your voice recording"
				width={50}
				height={50}
			/>
		</div>
	);

	const AlternativeUpload = ({ audioURL }) => (
		<div className="bg-white-500 p-2 inline-block">
			<p className="py-2">Alternatively, download and upload manually.</p>
			<div className="flex justify-center">
				<a href={audioURL} download className="px-4 py-2 bg-gray-200 rounded">Download</a>
			</div>
		</div>
	);

// In the main component...
	return (
		<div className="flex flex-col items-center p">
			{audioURL && <AudioPlayer audioURL={audioURL} duration={duration} />}
			<br/>
			<button
				className="p-2 rounded"
				onClick={recording ? stopRecording : startRecording}
				disabled={Boolean(uploadStatus)}
			>
				{ Boolean(uploadStatus)
					? uploadStatus
					: recording
						? <RecordingButton recordingElapsedTime={recordingElapsedTime} />
						: <StartRecordingButton />
				}

				{uploadSuccess === false && <AlternativeUpload audioURL={audioURL} />}
			</button>
		</div>
	);
}
