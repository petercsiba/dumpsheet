import { createServerComponentClient } from "@supabase/auth-helpers-nextjs";
import { cookies } from "next/headers";
import AudioUploadForm from "@/app/upload/components/AudioUploadForm";

export const dynamic = "force-dynamic";

export default async function Index() {

  return (
      <AudioUploadForm />
  );
}
