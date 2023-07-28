import React, { useState, FC } from 'react';

interface CollectEmailProcessingInfoProps {
    collectEmail: boolean | null;
    existingEmail: string | null;
    accountId: string;
}

const PRESIGNED_URL = 'https://api.voxana.ai/upload/voice';

const CollectEmailProcessingInfo: FC<CollectEmailProcessingInfoProps> = ({ collectEmail, existingEmail, accountId }) => {
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

        try {
            const response = await fetch(PRESIGNED_URL, {
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
            setMessage(`Please send the error message "${err}" alongside the reference ${accountId} to support@voxana.ai. Apologies for inconvenience`);
            setShowForm(false)
            console.error(err);
        }
    };

    return (
        <div className="p-4 text-left">
            {showForm && (
                collectEmail ? (
                    // TODO(P1, design): Make these align all into the center somehow.
                    <div className="p-4 text-center">
                        <p>
                            I will be processing your request in the next few minutes, please
                            enter your email to receive the results directly to your
                            inbox
                        </p>
                        <input
                            type="text"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="border p-2 rounded"
                        />
                        {(submitted || email.length >= 10) && !isEmailValid(email) &&
                            <p className="text-red-500">Invalid email address</p>
                        }
                        <button onClick={handleSubmit} className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                            Submit
                        </button>
                    </div>
                ) : (
                    <p>
                        I will be sending the result to your email {existingEmail ?? email} in a few minutes
                    </p>
                )
            )}
            <p>{message}</p>
        </div>
    );
}

export default CollectEmailProcessingInfo;