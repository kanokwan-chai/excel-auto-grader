import type { Metadata } from "next";
import { Noto_Sans_Thai, Sarabun } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/hooks/use-auth";
import { ToastProvider } from "@/components/ui/toast";

const notoThai = Noto_Sans_Thai({
  subsets: ["thai", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-noto-thai",
});

const sarabun = Sarabun({
  subsets: ["thai", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sarabun",
});

export const metadata: Metadata = {
  title: "Excel Auto Grader | ระบบตรวจงาน Excel อัตโนมัติสำหรับครู",
  description:
    "Multi-Teacher SaaS Platform สำหรับตรวจสูตร ผลลัพธ์ รูปแบบ และแผนภูมิ Microsoft Excel อัตโนมัติ พร้อมเชื่อมต่อ Google Classroom หลายบัญชี",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th" className={`${notoThai.variable} ${sarabun.variable}`}>
      <body className="min-h-screen bg-[#FFFDF9] font-sans antialiased text-violet-950">
        <ToastProvider>
          <AuthProvider>{children}</AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
