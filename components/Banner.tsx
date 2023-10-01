import {useRouter} from "next/router";
import Image from "next/image";

const Banner = () => {
    const router = useRouter();
    const {hubspot_status, account_id} = router.query;

    return (
        <div>
            <div className="w-full bg-green-500 flex items-center justify-center mt-4 pb-4">
                <div className="flex flex-col items-center px-8">
                    <Image
                        src="/images/voxana-logo-text-rectangle.png"
                        alt="Voxana AI Logo"
                        width={150}
                        height={30}
                    />
                </div>
                <a href="https://calendly.com/katka-voxana/30min?month=2023-10" target="_blank" rel="noopener noreferrer">
                    <span className="bg-black text-white font-semibold text-lg py-2 px-4 rounded">
                            Book a demo
                    </span>
                </a>
            </div>
            {hubspot_status === 'success' && (
                <div className="w-full bg-green-500 p-4 flex items-center justify-center">
                    <span className="text-black font-semibold px-2">
                        Successfully connected to <span style={{
                        backgroundColor: '#FF7A59'
                        }}>HubSpot!</span> Lets do your first recording
                    </span>
                </div>
            )}
            {hubspot_status === 'failure' && (
                <div className="w-full bg-red-500 p-4 flex items-center justify-center">
                    <span className="text-black font-semibold px-2">
                        Failed to connect to <span style={{
                        backgroundColor: '#FF7A59'
                    }}>HubSpot!</span> Please reach out to support@voxana.ai
                    </span>
                </div>
            )}
        </div>
    );
};

export default Banner;
