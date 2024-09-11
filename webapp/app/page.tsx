import Link from "next/link";

// import hero from "/public/dumpsheet-agent.webp";
import hero from "/public/images/evolution-trend-reverted-home-erectus-is-back.jpg"

import { Button } from "@/components/ui/button";
import ExplainerSection from "@/components/ExplainerSection";
import PricingSection from "@/components/PricingSection";

export const dynamic = "force-dynamic";

export default async function Index() {
  return (
      <div className="flex flex-col items-center pt-16">
          <div className="flex flex-col lg:flex-row items-center gap-8 p-8 max-w-6xl w-full">
              <div className="flex flex-col space-y-4 lg:w-1/2 w-full">
                  <h1 className="text-5xl font-bold">
                      GPT like it's the 90s.
                  </h1>
                  <p className="text-gray-600 text-lg">
                      No apps, just email. <br/>
                      No scam subscriptions, just invoices. <br/>
                      This is <b>Audio To Email</b>. <br/>
                  </p>
                  <div className="flex flex-row items-center">
                      <div>
                          <Link href="/upload" className="flex-grow-0">
                              <Button className="px-4 py-2 whitespace-nowrap">Upload Voice Memo's You Always Wanted to
                                  Revisit But Were Too Busy</Button>
                          </Link>
                      </div>
                  </div>
                  <div className="flex flex-row items-center">
                      <div className="text-sm text-gray-500 italic flex-grow ml-2">
                          Join hundreds who are redefining email productivity.

                          Just like in the good old days of calling your assistant
                          to transcribe your brain farts of gold for you.
                      </div>
                  </div>
                  <div className="mt-4 text-gray-500">
                      <span>Already a user? </span>
                      <Link className="text-blue-600 hover:underline" href="/login">
                          Sign In
                      </Link>
                  </div>
              </div>
              <div className="lg:w-1/2 w-full mt-8 lg:mt-0">
                  <img
                      src={hero.src}
                      alt="Voice to Email Conversion Illustration"
                      className="rounded-lg object-cover w-full h-full"
                  />
              </div>

          </div>
          <ExplainerSection/>
          <PricingSection/>

          <div className="w-full max-w-6xl mt-6 mb-2 p-8 rounded-lg space-y-8">
              <h2 className="text-3xl font-bold text-center mb-8">Still not convinced?</h2>
              <p className="text-gray-600 text-lg text-center">
                  <a href="https://www.loom.com/share/1614e907aeea4312bb53affd99677593" target="_blank"
                     rel="noopener noreferrer">

                      <Button>Let People From Ivy League Sell It To You</Button>
                  </a>
              </p>
              <p className="text-sm text-gray-600 text-center">
                  {/*TODO(P1, ux): Figure out how to start the voice recorder in the Demo mode */}
                  <Link href="/record/demo" className="flex-grow-0">
                      <Button className="px-4 py-2 whitespace-nowrap">Go Through Interactive Demo</Button>
                  </Link>
              </p>
          </div>

          <div className="w-full max-w-6xl mt-6 mb-6 p-8 rounded-lg space-y-8">
              <h2 className="text-3xl font-bold text-center mb-8">You In A Good Club</h2>

              <p className="text-sm text-gray-600 text-center">
                  Join Professionals from these companies who are already using Audio To Email:
              </p>

              <div className="flex justify-center items-center space-x-8">
                  <img src="/images/logos/experience-robinhood.png" alt="Robinhood" className="h-16"/>
                  <img src="/images/logos/experience-columbia-university.png" alt="Columbia University"
                       className="h-16"/>
                  <img src="/images/logos/experience-google.png" alt="Google" className="h-16"/>
                  <img src="/images/logos/experience-ibm.png" alt="IBM" className="h-16"/>
                  <img src="/images/logos/experience-mckinsey-and-company.png" alt="McKinsey and Company"
                       className="h-16"/>
                  <img src="/images/logos/experience-siemens.png" alt="Siemens" className="h-16"/>
              </div>
          </div>


          <div className="w-full max-w-6xl mt-6 mb-6 p-8 rounded-lg space-y-8">
              <h2 className="text-3xl font-bold text-center mb-8">We Are Here To Support You</h2>

              <div className="text-sm text-gray-600 text-center">
                  <div className="flex justify-center items-center space-x-4">
                      <Link href="mailto:support@dumpsheet.com">
                          <Button className="px-4 py-2 whitespace-nowrap">Email Peter</Button>
                      </Link>
                      <Link href="tel:+16502106516">
                          <Button className="px-4 py-2 whitespace-nowrap">Call Peter</Button>
                      </Link>
                  </div>
              </div>
          </div>
      </div>
          );
          }
