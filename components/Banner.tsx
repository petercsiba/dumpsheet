import {useRouter} from "next/router";

const Banner = () => {
    const router = useRouter();
    const {hubspot_status, account_id} = router.query;

    return (
        <div>
            {hubspot_status === 'success' && (
                <div className="w-full bg-green-500 p-4 flex items-center justify-center">
                    <span className="text-black font-semibold px-2">
                        Successfully connected to HubSpot! Lets do your first recording
                    </span>
                </div>
            )}
            {hubspot_status === 'failure' && (
                <div className="w-full bg-red-500 p-4 flex items-center justify-center">
                    <span className="text-black font-semibold px-2">
                        Failed to connect to HubSpot! Please reach out to support@voxana.ai
                    </span>
                </div>
            )}

            <div className="w-full bg-green-500 p-4 flex items-center justify-center">
                <a href="https://calendly.com/katka-voxana/30min?month=2023-10" target="_blank" rel="noopener noreferrer">
                    <span className="bg-black text-white font-semibold text-lg py-2 px-4 rounded">
                            Book a demo
                    </span>
                </a>
            </div>
        </div>
    );
};

export default Banner;
