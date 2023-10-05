import React, { useState, FC } from 'react';

interface CollectEmailProcessingInfoProps {
    collectEmail: boolean | null;
    existingEmail: string | null;
    accountId: string | null;
}

const UPDATE_EMAIL_URL = 'https://api.voxana.ai/upload/voice';

const CollectEmailProcessingInfo: FC<CollectEmailProcessingInfoProps> = ({ collectEmail, existingEmail, accountId}) => {
    const [email, setEmail] = useState('');
    const [message, setMessage] = useState('');
    const [submitted, setSubmitted] = useState(false);
    const [showForm, setShowForm] = useState(collectEmail !== null && collectEmail !== undefined);

    // Function to validate email
    const isEmailValid = (email: string) => {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/; // regex for more detailed email verification
        return regex.test(email);
    }

    const handleSubmit = async () => {
        console.log(`handleSubmit isEmailValid ${isEmailValid(email)}`)
        setSubmitted(true);
        // detailed email validation
        if (!isEmailValid(email)) {
            return;
        }
        // setMessage(`Processing email submission ...`);
        // setShowForm(false)

        try {
            const response = await fetch(UPDATE_EMAIL_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    email: email,
                    account_id: accountId,
                })
            });

            if (response.status >= 200 && response.status < 300) {
                setMessage(`Thanks! I will be sending the results to your email ${email}`);
                setShowForm(false)
            }
        } catch (err) {
            setMessage(`Ugh - an error occurred when setting your email. 
            Rest assured - we got your recording and our team was notified.`);
            setShowForm(false)
            console.error(`
                Please send the error message "${err}" alongside the reference ${accountId} to support@voxana.ai. Apologies for inconvenience`
            );
        }
    };

    return (
        <div className="p-4 text-left">
            {showForm && (
                collectEmail ? (
                    // TODO(P1, design): Make these align all into the center somehow.
                    <div className="text-left pl-6">
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
                        <div className="flex justify-center pt-2">
                            <button onClick={handleSubmit} className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                                Submit
                            </button>
                        </div>
                    </div>
                ) : (
                    <div>
                        <span className="font-bold text-lg">I will be:</span>
                        <ul className="list-disc list-inside ml-5 text-">
                            <li className="mt-1">Creating HubSpot Entries (if connected)</li>
                            <li className="mt-1">Sending results to <b>{existingEmail ?? email}</b></li>
                        </ul>
                    </div>
                )
            )}
            <p>{message}</p>
        </div>
    );
}

export default CollectEmailProcessingInfo;