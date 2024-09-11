import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function PricingSection() {
  return (
    <div className="w-full max-w-6xl mt-16 mb-6 p-8 rounded-lg space-y-8">
      <h2 className="text-3xl font-bold text-center mb-8">Pricing</h2>
      <div className="flex flex-wrap justify-center lg:space-x-4 space-y-4 lg:space-y-0 items-stretch">
        {pricingOptions.map((option, index) => (
          <div
            key={index}
            className={`flex flex-col border rounded-lg p-4 w-full lg:w-1/4 ${option.bgColor}`}
          >
            <div className="flex-grow space-y-4">
              <h3 className="text-2xl font-semibold text-center">
                {option.title}
              </h3>
              <p className="text-xl font-bold text-center mb-2">
                {option.price}
              </p>
              <p className="text-sm text-gray-600 text-center">
                {option.description}
              </p>
              <ul className="space-y-2 mb-4 pl-4">
                {option.features.map((feature, fIndex) => (
                  <li key={fIndex} className="flex items-center space-x-2">
                    <span className="text-green-500">✔</span>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="mt-10 text-center">
              <Link href={option.buttonHref}>
                {" "}
                <Button className="w-3/4">{option.buttonText}</Button>
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const pricingOptions = [
  {
    title: "Goodwill",
    price: "Free",
    description:
      "I am busy just give me your free sample",
    features: [
      "~15min of audio per day",
      "No Account Needed",
      "If you try to abuse it, Bad Karma will know.",
      "Your Access Code: 1876",
    ],
    buttonText: "Record Audio",
    buttonHref: "/record",
    bgColor: "bg-white",
  },
  {
    title: "Invoice",
    price: "2x of our compute cost",
    description:
      "This is how much $1 gets you:",
    features: [
      "50min of transcription",
      "5hr of audio text post-processing",
      "40min of calls",
    ],
    buttonText: "Choose More",
    buttonHref: "/login",
    bgColor: "bg-blue-50",
  },
  {
    title: "Enterprise",
    price: "Lets Negotiate",
    description: "The best value for \"high volumes\" (pun intended - we can handle your yelling!).",
    features: [
      "Lower cost for bulk purchases",
    ],
    buttonText: "Choose Premium",
    buttonHref: "/login",
    bgColor: "bg-white",
  },
];
