import { AvatarIcon } from "@radix-ui/react-icons";
import { createServerComponentClient } from "@supabase/auth-helpers-nextjs";
import { cookies } from "next/headers";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import React from "react";
import { Database } from "@/types/supabase";
import ClientSideCredits from "@/components/realtime/ClientSideCredits";

export const dynamic = "force-dynamic";

const stripeIsConfigured = process.env.NEXT_PUBLIC_STRIPE_IS_ENABLED === "true";

export const revalidate = 0;

const SoonBadge = () => {
  return (
    <span className="relative -top-2 -left-3 bg-gray-500 text-white text-xs font-bold px-2 py-1 rounded-full">
      Soon
    </span>
  );
};


export default async function Navbar() {
  const supabase = createServerComponentClient<Database>({ cookies });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const {
    data: credits,
  } = await supabase.from("credits").select("*").eq("user_id", user?.id ?? '').single()

  return (
    <div className="flex w-full px-4 lg:px-40 py-4 items-center border-b text-center gap-8 justify-between">
      <div className="flex gap-2 h-full">
        <Link href="/">
          <h2 className="font-bold pt-1.5 pr-2">GPT Like a Boomer</h2>
        </Link>
        <Link href="mailto:ai@mail.dumpsheet.com?subject=Attached%20Are%20My%20Audio%20Files">
          <Button variant={"ghost"} className="px-2">Attach Audio via Email</Button>
        </Link>
        <Link href="/record">
          <Button variant={"ghost"} className="px-2">Record Voice Mail</Button>
        </Link>
        <Link href="/upload">
          <Button variant={"ghost"} className="px-2">Upload from your PC</Button>
        </Link>
        {/*<Link href="/upload">*/}
        {/*  <Button variant={"ghost"} className="px-2">Send us Direct Mail</Button>*/}
        {/*</Link>*/}
        <Link href="tel:+18554137047">
          <Button variant={"ghost"} className="px-2">Dial Up GPT <br />+1 (855) 413-7047</Button>
        </Link>
        {/*<Link href="mailto:support@gptboomer.com?subject=Support%20Request">*/}
        {/*  <Button variant={"ghost"} className="px-2" style={{ fontFamily: 'Courier, monospace'}}>Send a Fax</Button>*/}
        {/*</Link>*/}
        <Link href="/fax">
          <Button variant={"ghost"} className="px-4">Fax</Button>
          <SoonBadge />
        </Link>
        <Link href="/direct-mail">
          <Button variant={"ghost"} className="px-2">Direct Mail</Button>
          <SoonBadge />
        </Link>
      </div>
      {user && (
          <div className="hidden lg:flex flex-row gap-2">
            {stripeIsConfigured && (
            <Link href="/get-credits">
              <Button variant={"ghost"}>Get Credits</Button>
            </Link>
          )}
        </div>
      )}
      <div className="flex gap-4 lg:ml-auto">
        {!user && (
          <Link href="/login">
            <Button>Login / Signup</Button>
          </Link>
        )}
        {user && (
          <div className="flex flex-row gap-4 text-center align-middle justify-center">
            {stripeIsConfigured && (
              <ClientSideCredits creditsRow={credits ? credits : null} />
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild className="cursor-pointer">
                <AvatarIcon height={24} width={24} className="text-primary" />
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56">
                <DropdownMenuLabel className="text-primary text-center overflow-hidden text-ellipsis">{user.email}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <form action="/auth/sign-out" method="post">
                  <Button
                    type="submit"
                    className="w-full text-left"
                    variant={"ghost"}
                    >
                    Log out
                  </Button>
                </form>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
    </div>
  );
}
