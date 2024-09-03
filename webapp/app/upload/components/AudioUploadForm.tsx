"use client";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormDescription,
  FormLabel,
} from "@/components/ui/form";
import { useToast } from "@/components/ui/use-toast";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import {DropEvent, FileRejection, useDropzone} from "react-dropzone";
import { SubmitHandler, useForm } from "react-hook-form";
import { FaImages } from "react-icons/fa";
import * as z from "zod";
import {formatFileSizeShort} from "../../../src/number-utils";

const fileUploadFormSchema = z.object({
  name: z
    .string()
    .min(1)
    .max(255) // Increased max length to accommodate more typical file names
    .regex(/^[a-zA-Z0-9 _.-]+$/, "Invalid characters in file name"),
  type: z.string().min(1).max(50),
});

type FormInput = z.infer<typeof fileUploadFormSchema>;

const stripeIsConfigured = process.env.NEXT_PUBLIC_STRIPE_IS_ENABLED === "true";

export default function AudioUploadForm() {
  const [files, setFiles] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const { toast } = useToast();
  const router = useRouter();

  const form = useForm<FormInput>({
    resolver: zodResolver(fileUploadFormSchema),
    defaultValues: {
      name: "",
      type: "man",
    },
  });

  const onSubmit: SubmitHandler<FormInput> = () => {
    // TODO(P0, feature): Actually implement the form submission based on record/page.tsx
    uploadEverything();
  };

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const newFiles: File[] =
        acceptedFiles.filter(
          (file: File) => !files.some((f) => f.name === file.name)
        ) || [];

      // if user tries to upload more than 10 files, display a toast
      if (newFiles.length + files.length > 100) {
        toast({
          title: "Too many files",
          description:
            "You can only upload up to 100 files in total. Please try again.",
          duration: 5000,
        });
        return;
      }

      // display a toast if any duplicate files were found
      if (newFiles.length !== acceptedFiles.length) {
        toast({
          title: "Duplicate file names",
          description:
            "Some of the files you selected were already added. They were ignored.",
          duration: 5000,
        });
      }

      // check that in total images do not exceed a combined 2GB
      const totalSize = files.reduce((acc, file) => acc + file.size, 0);
      const newSize = newFiles.reduce((acc, file) => acc + file.size, 0);

      if (totalSize + newSize > 2 * 1024 * 1024 * 1024) {
        toast({
          title: "Integer Overflow you got us! Just joking, it's just too much to upload",
          description:
            "The total combined size of the audio and video files cannot exceed 2GB.",
          duration: 5000,
        });
        return;
      }

      setFiles([...files, ...newFiles]);

      toast({
        title: "Files selected",
        description: "The files were successfully selected.",
        duration: 5000,
      });
    },
    [files]
  );

  const removeFile = useCallback(
    (file: File) => {
      setFiles(files.filter((f) => f.name !== file.name));
    },
    [files]
  );

  const uploadEverything = useCallback(async () => {
    setIsLoading(true);
    // Upload each file to Amazon S3

    toast({
      title: "Fake uploading",
      description: "Throwing the files into the cloud bucket...",
      duration: 5000,
    });

    setIsLoading(false);

    toast({
      title: "Files queued for transcription",
      description:
        "The files were queued for transcription. You will receive an email when our job is done.",
      duration: 5000,
    });

    router.push("/status");
  }, [files]);

  // Handle files that are rejected by the dropzone
  const handleDropRejected = (fileRejections: FileRejection[], event: DropEvent) => {
    // Generate a message detailing the rejected files and the specific reasons
    const rejectionMessages = fileRejections.map(({ file, errors }) => {
      // Join all error messages for a single file
      const errorMessages = errors.map(error => error.message).join(', ');
      return `${file.name}: ${errorMessages}`;
    }).join('\n');

    // Display a toast with the detailed rejection messages
    toast({
      title: "Unsupported File Type",
      description: `Some files were rejected for the following reasons:\n${rejectionMessages}`,
      duration: 5000,
    });
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected: handleDropRejected,
    // NOTE: If needed we can restrict the file types depending on what ffmpeg can handle here,
    // e.g.: "audio/*": [".mp3", ".wav", ".ogg", ".m4a"],
    accept: {
      "audio/*": [],  // Accepts any audio file
      "video/*": []   // Accepts any video file
    },
  });

  return (
    <div>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="rounded-md flex flex-col gap-8"
        >
          <div
            {...getRootProps()}
            className=" rounded-md justify-center align-middle cursor-pointer flex flex-col gap-4"
          >
            <FormLabel>Audio and Video Files</FormLabel>
            <FormDescription>
              Upload 1-100 files with a combined size of what you think your Internet can handle.
            </FormDescription>
            {/*TODO(P2, ux): This area overflows a bit weirdly when too many files are present */}
            <div className="outline-dashed outline-2 outline-gray-100 hover:outline-blue-500 w-full h-full rounded-md p-4 flex justify-center align-middle" style={{ height: '20vh' }}>
              <input {...getInputProps()} />
              {isDragActive ? (
                <p className="self-center">Drop the files here ...</p>
              ) : (
                <div className="flex justify-center flex-col items-center gap-2">
                  <FaImages size={32} className="text-gray-700" />
                  <p className="self-center">
                    Drag 'n' drop audio / video files here, or click to select files.
                  </p>
                </div>
              )}
            </div>
          </div>
          {files.length > 0 && (
            <div className="flex flex-row gap-4 flex-wrap">
              {files.map((file) => (
                <div key={file.name} className="flex flex-col gap-1">
                  <p className="self-center">
                      {file.name} ({formatFileSizeShort(file.size)})
                  </p>
                  <Button
                    variant="outline"
                    size={"sm"}
                    className="w-full"
                    onClick={() => removeFile(file)}
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          )}

          <Button type="submit" className="w-full" isLoading={isLoading}>
            Upload Files{" "}
            {stripeIsConfigured && <span className="ml-1">(Might cost you sth)</span>}
          </Button>
        </form>
      </Form>
    </div>
  );
}