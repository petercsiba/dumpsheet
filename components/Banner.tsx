import {useRouter} from "next/router";
import Image from "next/image";
import ConnectHubspotButton from "@/components/ConnectHubspotButton";

const Banner = () => {
    const router = useRouter();
    const {hubspot_status, account_id} = router.query;

    return (
        <>
            <div className="absolute top-8 left-8 flex items-center space-x-2 top-navigation">
                <a href="https://www.voxana.ai/">
                    <Image
                        src="/images/voxana-logo-text-rectangle-930x174-transparent.png"
                        alt="Voxana AI Logo"
                        width={150}
                        height={30}
                    />
                </a>
                {/*
                  <div className="flex items-center space-x-8 font-medium text-black text-lg tracking-tight">
                      <div>Features</div>
                      <div>Use cases</div>
                  </div>
                  */}
            </div>
            <div className="absolute top-6 right-8 flex items-center space-x-2">
                <a href="https://www.loom.com/share/396ae98d37ce404abd6bcc110905d7a3?sid=fbb9cfef-f607-4a1c-8245-53fdf9b8eb7c" target="_blank"
                   rel="noopener noreferrer">
                    <button
                        className="flex items-center justify-center w-40 h-12 bg-black rounded-full font-semibold text-white text-lg tracking-tighter hover:bg-gray-700">
                        Watch the Demo
                    </button>
                </a>
                {/*
                <div className="flex items-center justify-center w-12 h-12 bg-[#0000001a] rounded-full">
                    <Image className="group-8" alt="Group" src="/images/figma/group-1000004834.png" width={30}
                           height={30}/>
                </div>
                */}
            </div>
            {hubspot_status && (
                <div className="absolute top-20 left-1/2 transform -translate-x-1/2 flex flex-col items-center justify-center text-center border border-black rounded-full bg-white p-4 w-auto">
                    <div className="block text-black font-semibold text-center">
                        {hubspot_status === 'success' && <span className="text-green-700">Successfully connected your HubSpot!</span>}
                        {hubspot_status !== 'success' && <span className="text-red-600">Failed connecting your HubSpot!</span>}
                    </div>
                    <div className="block text-center">
                        {hubspot_status === 'success' ? 'Lets do your first recording' : 'Please reach out to support@voxana.ai'}
                    </div>
                </div>
            )}
        </>
    );
};

export default Banner;
