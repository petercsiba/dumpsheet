import {useRouter} from "next/router";
import Image from "next/image";

const Banner = () => {
    const router = useRouter();
    const {hubspot_status, account_id} = router.query;

    return (
        <>
            <div className="absolute top-6 left-4 flex items-center space-x-2 top-navigation">
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
            <div className="absolute top-3 right-4 flex items-center space-x-2">
                <a href="https://www.loom.com/share/1614e907aeea4312bb53affd99677593" target="_blank"
                   rel="noopener noreferrer">
                    <button
                        className="flex items-center justify-center w-40 h-12 bg-black rounded-full font-semibold text-white text-lg tracking-tighter hover:bg-gray-700">
                        Watch Demo
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
                <div className="absolute top-20 left-1/2 transform -translate-x-1/2 flex flex-col items-center justify-center text-center border border-black lg bg-white px-6 py-1">
                    <div className="block text-black font-semibold text-center">
                        {hubspot_status === 'success' && <span className="text-green-700">Successfully connected your HubSpot!</span>}
                        {hubspot_status !== 'success' && <span className="text-red-500">Failed connecting your HubSpot!</span>}
                    </div>
                    <div className="block text-center">
                        {hubspot_status === 'success' ? 'Lets do your first recording' : 'Please reach out to support@voxana.ai'}
                    </div>
                </div>
            )}
            {!hubspot_status && (
                <div className="w-[16rem] absolute top-10 left-1/2 transform -translate-x-1/2 flex flex-col items-center justify-center text-center border border-black rounded-lg bg-white px-6 py-1">
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
