"use client"
import {useSearchParams} from "next/navigation";
import Image from "next/image";

type BannerProps = {};

const Banner: React.FC<BannerProps> = ({  }) => {
    const searchParams = useSearchParams()
    const hubspot_status = searchParams.get('hubspot_status');

    return (
        <>
            {hubspot_status && (
                <div className="absolute top-20 left-1/2 transform -translate-x-1/2 flex flex-col items-center justify-center text-center border border-black lg bg-white px-6 py-1">
                    <div className="block text-black font-semibold text-center">
                        {hubspot_status === 'success' && <span className="text-green-700">Successfully connected your HubSpot!</span>}
                        {hubspot_status !== 'success' && <span className="text-red-500">Failed connecting your HubSpot!</span>}
                    </div>
                    <div className="block text-center">
                        {hubspot_status === 'success' ? 'Lets do your first recording' : 'Please reach out to support@dumpsheet.com'}
                    </div>
                </div>
            )}
            {!hubspot_status && (
                <div className="w-[16rem] absolute top-20 left-1/2 transform -translate-x-1/2 flex flex-col items-center justify-center text-center border border-black rounded-lg bg-white px-6 py-1">
                    <div className="block text-black font-semibold text-center">
                        We are in Private Beta
                    </div>
                    <div className="block text-center">
                        Your feedback counts
                    </div>
                </div>
            )}
        </>
    );
};

export default Banner;
