import { createServerComponentClient } from "@supabase/auth-helpers-nextjs";
import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import hero from "/public/dumpsheet-agent.webp";

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
              Email, Effortlessly with Your Voice.
            </h1>
            <p className="text-gray-600 text-lg">
              Transform your spoken words into written emails instantly with <b>Audio To Email</b>.
              Perfect for professionals on the go, accessibility needs, or anyone looking to streamline their workflow.
            </p>
            <div className="flex flex-row items-center">
              <div>
                <Link href="/record" className="flex-grow-0">
                  <Button className="px-4 py-2 whitespace-nowrap">Start Dictating Now</Button>
                </Link>
              </div>
              <div className="text-sm text-gray-500 italic flex-grow ml-2">
                Join thousands who are redefining email productivity. Fast, accurate, and secure.
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

        <div className="w-full max-w-6xl mt-16 mb-16 p-8 rounded-lg space-y-8">
          <h2 className="text-3xl font-bold text-center mb-8">Still not convinced?</h2>
          <p className="text-gray-600 text-lg text-center">
            <a href="https://www.loom.com/share/1614e907aeea4312bb53affd99677593" target="_blank"
               rel="noopener noreferrer">

                <Button>Watch Demo</Button>
            </a>
          </p>
        </div>
      </div>
  );
}
