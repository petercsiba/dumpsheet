import { useEffect, useState } from 'react'
import RecordRTC from 'recordrtc'
import Image from 'next/image'
import MicrophoneIcon from '../public/images/icons/microphone-icon.svg'
import StopIcon from '../public/images/icons/stop-icon.svg'

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

	const stopRecording = async () => {
		if (!recording) {
			return
		}
		recording.stopRecording(async () => {
			const audioBlob = recording.getBlob();
			const audioURL = URL.createObjectURL(audioBlob);
			const minDuration = 10
			// More proper might be audio.onloadedmetadata, but somehow doesn't work.
			console.log(`check recoding long enough ${recordingElapsedTime} >= ${minDuration}`)
			if (recordingElapsedTime < minDuration) {
				setUploadStatus('Recording needs to be longer than ' + minDuration + ' seconds, please try again.');
				setTimeout(() => {
					// This block of code will be executed after a delay of 2.5 seconds
					console.log(`recording short auto-refresh`)
					setRecording(null)  // should also reset the elapsedTime
					setUploadStatus(null)
				}, 2500);
				return
			}

			// This will also show the recording box
			setAudioURL(audioURL);

			// Upload to API
			const formData = new FormData();
			formData.append('audio', audioBlob);

			setUploadStatus('Uploading...');

			try {
				const response = await Promise.race([
					fetch('http://api.voxana.ai/uploads/', {
						method: 'POST',
						body: formData
					}),
					new Promise((_, reject) =>
						setTimeout(() => reject(new Error('Timeout')), 20000)
					)
				]);

				setUploadSuccess(response.status >= 200 && response.status < 300)

				if (response.status >= 200 && response.status < 300) {
					// Successful upload, you can handle it appropriately.
					setUploadStatus('Uploaded successfully!');
				} else if (response.status >= 400 && response.status < 500) {
					// Handle frontend error, maybe set some state here
					setUploadStatus('Uh-oh, something went wrong on our end (HTTP ' + response.status + '). Please try again.');
				} else if (response.status >= 500 && response.status < 600) {
					// Handle server error, maybe set some state here
					setUploadStatus('Sorry, something went wrong on our servers (HTTP ' + response.status + '). Please contact support@voxana.ai');
				} else {
					// Handle other cases or throw an error if you want
					setUploadStatus('Something went wrong. Please try again later. If the problem persists, contact support@voxana.ai');
				}
			} catch (error) {
				if (error.message === 'Timeout') {
					setUploadStatus('Your request timed out. Please check your internet connection.');
				} else {
					console.error("Failed to upload recording: ", error)
					setUploadStatus('Failed to upload the recording. Please try again or send this to support@voxana.ai: ' + error);
				}
			} finally {
				setRecording(null);
			}
		});
	};

	return (
		<div className="flex flex-col items-center p">
			{audioURL && (
				<div>
					<audio className="pl-8 pr-8" src={audioURL} controls />
					<p className="flex justify-center">Duration: {formatDuration(duration)}</p>
				</div>
			)}
			<br/>
			<button
				className="p-2 rounded"
				onClick={recording ? stopRecording : startRecording}
				disabled={Boolean(uploadStatus)}
			>
				{ Boolean(uploadStatus) ? uploadStatus
					: recording ?
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
					:
				<div className="bg-gray-200 p-2 inline-block rounded-full border-2 border-black">
						<Image
						priority
						src={MicrophoneIcon}
						alt="Start your voice recording"
						width={50}
						height={50}
					/>
				</div>
				}

				{uploadSuccess === false && (
					<div className="bg-white-500 p-2 inline-block">
						<p className="py-2">Alternatively, download and upload manually.</p>
						<div className="flex justify-center">
							<a href={audioURL} download className="px-4 py-2 bg-gray-200 rounded">Download</a>
						</div>
					</div>
				)}
			</button>
		</div>
	)
}
