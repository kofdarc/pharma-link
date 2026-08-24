"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api-client";
import { Notice } from "@/components/ui/Notice";
import { Button } from "@/components/ui/Button";
import { BrandMark } from "@/components/ui/BrandMark";

export default function VerifyEmailPage() {
  const params = useParams<{ uid: string; token: string }>();
  const [status, setStatus] = useState<"checking" | "done" | "error">("checking");
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch("/auth/verify-email/", {
      method: "POST",
      body: JSON.stringify({ uid: params.uid, token: params.token })
    })
      .then(() => setStatus("done"))
      .catch((exception) => {
        setError((exception as ApiError).message || "This verification link is invalid or has expired.");
        setStatus("error");
      });
  }, [params.uid, params.token]);

  return (
    <div className="center-screen">
      <div className="auth-card">
        <Link href="/" className="brand">
          <BrandMark />
          <span>HealthConnect</span>
        </Link>
        <h1>Verify your email</h1>

        {status === "checking" ? <div className="skeleton-card" /> : null}
        {status === "done" ? (
          <>
            <Notice tone="success">Your email is verified. You can now place orders.</Notice>
            <Button type="button" onClick={() => (window.location.href = "/shop")}>
              Continue to HealthConnect
            </Button>
          </>
        ) : null}
        {status === "error" ? (
          <>
            <Notice tone="danger">{error}</Notice>
            <p className="muted small">
              Request a new link from <Link href="/login">the login page</Link>.
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
