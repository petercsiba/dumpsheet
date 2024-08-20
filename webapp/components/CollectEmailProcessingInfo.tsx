import React, {useState, FC} from 'react';

interface CollectEmailProcessingInfoProps {
    accountId: string | null;
    onRegistrationSuccess: (emailAddress: string) => void;
}

const UPDATE_EMAIL_URL = 'https://api.dumpsheet.com/upload/voice';

const CollectEmailProcessingInfo: FC<CollectEmailProcessingInfoProps> = ({accountId, onRegistrationSuccess}) => {
    const [email, setEmail] = useState('');
    const [errorMessage, setErrorMessage] = useState('');
    const [submitted, setSubmitted] = useState(false);
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

            // TODO(P0, ux): We can use React store to store email / account so next time don't need to type in.
            if (response.status >= 200 && response.status < 300) {
                onRegistrationSuccess(email)  // callback -> navigate away
            }
        } catch (err) {
            setErrorMessage(`Oh no! An error occurred when setting your email. 
            Rest assured - we got your recording and our team was notified.`);
            console.error(`
                Please send the error message "${err}" alongside the reference to support@dumpsheet.com - Apologies for inconvenience`
            );
        }
    };

    return (
        <div className="text-left">
            {/* TODO(P1, design): Make these align all into the center somehow. */}
            <p>
                I will be processing your request in the next few minutes.
            </p>

            {/* == EMAIL INPUT == */}
            <p className="pt-2">
                Please <b>enter your email</b> to receive results of my work directly into your inbox:
            </p>
            <div className="flex justify-center pt-2">
                {/* TODO(P1, ux): It should remember last entry */}
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

            {/* == ACCEPT ToS == */}
            <div className="flex items-center justify-center pt-2">
                <input
                    type="checkbox"
                    checked={termsAccepted}
                    onChange={(e) => setTermsAccepted(e.target.checked)}
                />
                <label className="ml-2">
                    Agree to our&nbsp;
                    <a className="underline hover:no-underline"
                       // TODO(P1, dumpsheet migration): Does this even exist?
                       href="https://www.dumpsheet.com/legal/terms-of-service" target="_blank"
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

            {/* == ERROR MESSAGE == */}
            <p className="text-red-500">{errorMessage}</p>
        </div>
    );
}

export default CollectEmailProcessingInfo;