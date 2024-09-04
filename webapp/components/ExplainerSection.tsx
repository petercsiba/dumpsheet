import Link from "next/link";
import blur from "/public/dumpsheet-email-result-blurred.webp";
import example from "/public/dumpsheet-example-upload.webp";
import result from "/public/dumpsheet-email-result.webp";
import {Button} from "@/components/ui/button";

export default function ExplainerSection() {
  return (
    <div className="w-full max-w-6xl mt-16 p-8 bg-gray-100 rounded-lg space-y-8">
      <h2 className="text-3xl font-bold text-center mb-8">How It Works</h2>

      {/* Step 1: Upload your audio */}
      <div className="space-y-4">
        <div className="flex items-center justify-center space-x-4">
          <div
              className="text-3xl font-bold text-blue-600 bg-white border-2 border-blue-600 rounded-full w-10 h-10 flex items-center justify-center">
            1
          </div>
          <h3 className="text-2xl font-semibold">Upload or Record your Audio</h3>
        </div>
        <p className="text-sm text-gray-600 text-center">
          Any audio file would do, or you can <Link href="/record">record one </Link> right here!.
        </p>
        <img
            src={example.src}
            alt="Audio file upload example"
            className="rounded-lg object-cover w-3/4 md:w-1/2 lg:w-1/3 mx-auto"
        />
        <p className="text-sm text-gray-600 text-center">
          <Link href="/record/demo" className="flex-grow-0">
            <Button className="px-4 py-2 whitespace-nowrap">Interactive Demo</Button>
          </Link>
        </p>
      </div>

      {/* Step 2: Ba */}
      <div className="space-y-4">
        <div className="flex items-center justify-center space-x-4">
          <div
              className="text-3xl font-bold text-blue-600 bg-white border-2 border-blue-600 rounded-full w-10 h-10 flex items-center justify-center">
            2
          </div>
          <h3 className="text-2xl font-semibold">Our Agents get to Work</h3>
        </div>
        <p className="text-sm text-gray-600 text-center">
          Only takes a few minutes as you grab your drink of choice on your way to your desk.
        </p>
        <img
            src={blur.src}
            alt="Transcribed audio result blurred"
            className="rounded-lg object-cover w-3/4 md:w-1/2 lg:w-1/3 mx-auto"
        />
      </div>

      {/* Step 3: Generate images */}
      <div className="space-y-4">
        <div className="flex items-center justify-center space-x-4">
          <div className="text-3xl font-bold text-blue-600 bg-white border-2 border-blue-600 rounded-full w-10 h-10 flex items-center justify-center">
            3
          </div>
          <h3 className="text-2xl font-semibold">Your Voice Memo in your Mailbox</h3>
        </div>
        <p className="text-sm text-gray-600 text-center">
          Audio text ready for its next destination when you ready to do so!
        </p>
        <img
          src={result.src}
          alt="Transcribed audio result"
          className="rounded-lg object-cover w-3/4 md:w-1/2 lg:w-1/3 mx-auto"
        />
      </div>
    </div>
  );
}
