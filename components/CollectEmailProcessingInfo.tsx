import React, {useState, FC} from 'react';
import ProgressBar from "@/components/ProgressBar";

interface CollectEmailProcessingInfoProps {
    collectEmail: boolean | null;
    existingEmail: string | null;
    accountId: string | null;
}

const UPDATE_EMAIL_URL = 'https://api.voxana.ai/upload/voice';

const CollectEmailProcessingInfo: FC<CollectEmailProcessingInfoProps> = ({collectEmail, existingEmail, accountId}) => {
    const [email, setEmail] = useState('');
    const [message, setMessage] = useState('');
    const [submitted, setSubmitted] = useState(false);
    const [success, setSuccess] = useState(collectEmail === false);
    const [termsAccepted, setTermsAccepted] = useState(false);

    // Function to validate email
    const isEmailValid = (email: string) => {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/; // regex for more detailed email verification
        return regex.test(email);
    }

    const handleSubmit = async () => {
        console.log(`handleSubmit isEmailValid ${isEmailValid(email)} termsAccepted ${termsAccepted}`)
        setSubmitted(true);
        // detailed email validation
        if (!isEmailValid(email) || !termsAccepted) {
            return;
        }

        try {
            const response = await fetch(UPDATE_EMAIL_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    email: email,
                    tos_accepted: termsAccepted,
                    account_id: accountId,
                })
            });

            if (response.status >= 200 && response.status < 300) {
                setSuccess(true)
            }
        } catch (err) {
            setMessage(`Ugh - an error occurred when setting your email. 
            Rest assured - we got your recording and our team was notified.`);
            console.error(`
                Please send the error message "${err}" alongside the reference ${accountId} to support@voxana.ai. Apologies for inconvenience`
            );
        }
    };

    return (
        <div className="text-left">
            {!success && collectEmail && (
                // TODO(P1, design): Make these align all into the center somehow.
                <>
                    <p>
                        I will be processing your request in the next few minutes.
                    </p>
                    <p className="pt-2">
                        Please <b>enter your email</b> to receive results directly into your inbox:
                    </p>
                    <div className="flex justify-center pt-2">
                        <input
                            type="text"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="border p-2 rounded"
                        />
                    </div>
                    {(submitted || email.length >= 8) && !isEmailValid(email) &&
                        <p className="text-red-500">Invalid email address</p>
                    }
                    <div className="flex items-center justify-center pt-2">
                        <input
                            type="checkbox"
                            checked={termsAccepted}
                            onChange={(e) => setTermsAccepted(e.target.checked)}
                        />
                        <label className="ml-2">
                            <a className="underline hover:no-underline"
                               href="https://www.voxana.ai/legal/terms-of-service" target="_blank"
                               rel="noopener noreferrer">
                                terms of service
                            </a>
                        </label>
                    </div>
                    <div className="flex justify-center pt-2">
                        <button
                            onClick={handleSubmit}
                            className={`bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded ${!termsAccepted ? 'opacity-50 cursor-not-allowed' : ''}`}
                            disabled={!termsAccepted}
                        >
                            Submit
                        </button>
                    </div>
                    <ProgressBar currentStep={2}/>
                </>
            )}
            <p>{message}</p>
            {success && (
                <>
                    <p className="pl-4">
                        <span className="font-bold text-base">I will be:</span>
                        <ul className="list-disc list-inside text-">
                            <li className="mt-1">Sending results to <b>{existingEmail ?? email}</b></li>
                            <li className="mt-1">Syncing to HubSpot (if connected)</li>
                        </ul>
                    </p>
                    <ProgressBar currentStep={3}/>
                </>
            )}
        </div>
    );
}

export default CollectEmailProcessingInfo;