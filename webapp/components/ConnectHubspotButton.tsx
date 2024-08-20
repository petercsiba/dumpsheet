import Image from 'next/image';
import HubspotLogo from '../public/images/hubspot-logo.svg'

const HUBSPOT_CLIENT_ID: string = "501ffe58-5d49-47ff-b41f-627fccc28715";
// When changed - the Hubspot owners need to re-auth with Voxana
// Can be changed in the app admin: https://app.hubspot.com/developer/43920988/application/2150554
const HUBSPOT_SCOPES: string = "oauth crm.objects.contacts.write crm.objects.owners.read";
// TODO(p2, devx): Why this ain't working?
// const HUBSPOT_REDIRECT_URI: string = process.env.HUBSPOT_REDIRECT_URI || "http://localhost:3000"
const HUBSPOT_REDIRECT_URI: string = "https://api.dumpsheet.com/hubspot/oauth/redirect";
console.log(`hubspot config ${HUBSPOT_REDIRECT_URI} for scopes ${HUBSPOT_SCOPES}`)
// const HUBSPOT_OPTIONAL_SCOPE: string = encodeURIComponent("automation");

// Function to construct the authorization URL
function constructAuthUrl(accountId: any) {
    const state = encodeURIComponent("accountId:" + accountId)
    return `https://app.hubspot.com/oauth/authorize?client_id=${encodeURIComponent(HUBSPOT_CLIENT_ID)}&scope=${encodeURIComponent(HUBSPOT_SCOPES)}&redirect_uri=${encodeURIComponent(HUBSPOT_REDIRECT_URI)}&state=${state}`;
}

export default function ConnectHubspotButton() {
    return (
        <button
            id="connectWithHubspot"
            onClick={() => {
                // This can be null
                window.location.href = constructAuthUrl(localStorage.getItem("accountId"));
            }}
            className="flex items-center justify-center w-60 h-12 text-black border border-black rounded-full font-semibold text-lg tracking-tighter bg-white hover:bg-gray-100"
        >
            <span className="pr-2"> Connect your </span>
            <Image
                priority
                src={HubspotLogo}
                alt="HubSpot logo"
                width={85}
                height={24}
            />
        </button>
    );
}
