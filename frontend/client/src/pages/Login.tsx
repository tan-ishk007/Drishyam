/**
 * DRISHYAM visual reminder: a warm cinematic investigation room frames a crisp
 * cream authentication dossier; burgundy indicates secure access and legal authority.
 */
import { useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
import { toast } from "sonner";
import { ArrowRight, Check, Eye, EyeOff, FileText, Lock, MailCheck, Network, ShieldCheck, Smartphone, UserRound } from "lucide-react";
import { getPublicAuthConfig } from "@/api/auth";
import { getApiErrorMessage } from "@/api/client";
import { useSession } from "@/contexts/SessionContext";

const SCENE = {
  investigator: "/assets/auth-investigator-latest-reference-transparent.png",
  board: "/assets/auth-cinematic-board_6c19533e.png",
  lamp: "/assets/auth-cinematic-lamp_5dd09cd3.png",
};
const ENV_GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID || "").trim();
type Mode = "login" | "signup";
type OtpStage = "signup" | "login" | null;
const perks = [
  [ShieldCheck, "Preserve", "Secure and verify evidence with integrity."],
  [Network, "Connect", "Link patterns, entities and digital trails."],
  [FileText, "Prove", "Generate court-ready reports with confidence."],
] as const;

export default function Login() {
  const [, setLocation] = useLocation();
  const {
    user,
    isRestoring,
    signInWithPassword,
    register,
    verifyRegistration,
    resendRegistrationVerification,
    requestPasswordlessOtp,
    signInWithEmailOtp,
    signInWithGoogle,
  } = useSession();
  const [mode, setMode] = useState<Mode>(() => new URLSearchParams(window.location.search).get("mode") === "signup" ? "signup" : "login");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [otpStage, setOtpStage] = useState<OtpStage>(null);
  const [verificationCode, setVerificationCode] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [googleClientId, setGoogleClientId] = useState(ENV_GOOGLE_CLIENT_ID);
  const googleButton = useRef<HTMLDivElement | null>(null);
  const update = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }));
  const openWorkspace = (description: string) => { toast.success("Secure access verified", { description }); setLocation("/workspace"); };

  useEffect(() => {
    if (!isRestoring && user) setLocation("/workspace");
  }, [isRestoring, setLocation, user]);

  useEffect(() => {
    if (googleClientId) return;
    getPublicAuthConfig().then((config) => setGoogleClientId((config.google_client_id || "").trim())).catch(() => undefined);
  }, [googleClientId]);

  useEffect(() => {
    if (!googleClientId || mode !== "login" || otpStage || !googleButton.current) return;
    const renderGoogleButton = () => {
      const google = (window as Window & { google?: any }).google;
      if (!google?.accounts?.id || !googleButton.current) return;
      google.accounts.id.initialize({
        client_id: googleClientId,
        callback: async ({ credential }: { credential: string }) => {
          setSubmitting(true);
          try { await signInWithGoogle(credential); openWorkspace("Your verified Google identity opened this in-memory session."); }
          catch (error) { setErrors({ form: getApiErrorMessage(error, "Google sign-in could not be completed.") }); }
          finally { setSubmitting(false); }
        },
      });
      googleButton.current.replaceChildren();
      const buttonWidth = Math.max(250, Math.floor(googleButton.current.getBoundingClientRect().width));
      google.accounts.id.renderButton(googleButton.current, { theme: "outline", size: "large", text: "continue_with", shape: "rectangular", width: buttonWidth });
    };
    const existing = document.querySelector<HTMLScriptElement>('script[data-drishyam-google-gis="true"]');
    if (existing) {
      existing.addEventListener("load", renderGoogleButton, { once: true });
      renderGoogleButton();
      return () => existing.removeEventListener("load", renderGoogleButton);
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.dataset.drishyamGoogleGis = "true";
    script.addEventListener("load", renderGoogleButton, { once: true });
    document.head.appendChild(script);
  }, [mode, otpStage, signInWithGoogle, googleClientId]);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = window.setTimeout(() => setResendCooldown((seconds) => Math.max(0, seconds - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [resendCooldown]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (otpStage) {
      if (!/^\d{6}$/.test(verificationCode)) next.otp = "Enter the 6-digit verification code";
    } else {
      if (mode === "signup" && !form.name.trim()) next.name = "Enter your full name";
      if (!form.email.trim()) next.email = "Enter your email";
      if (form.password.length < 12) next.password = "Use at least 12 characters";
      if (mode === "signup" && form.password !== form.confirm) next.confirm = "Passwords must match";
    }
    setErrors(next);
    if (Object.keys(next).length) return;
    setSubmitting(true);
    try {
      if (otpStage === "signup") {
        await verifyRegistration({ email: form.email.trim(), otp: verificationCode });
        openWorkspace("Your verified email activated this in-memory session.");
      } else if (otpStage === "login") {
        await signInWithEmailOtp({ email: form.email.trim(), otp: verificationCode });
        openWorkspace("Your email OTP opened this in-memory session.");
      } else if (mode === "login") {
        await signInWithPassword({ email: form.email.trim(), password: form.password });
        openWorkspace("Opening your authorized case workspace.");
      } else {
        await register({ name: form.name.trim(), email: form.email.trim(), password: form.password });
        setOtpStage("signup");
        setVerificationCode("");
        setResendCooldown(60);
        toast.info("Verification required", { description: "A six-digit code was sent by the configured email provider." });
      }
    } catch (error) {
      setErrors({ form: getApiErrorMessage(error, "Secure access could not be completed.") });
    } finally {
      setSubmitting(false);
    }
  };

  const requestOtp = async () => {
    if (!form.email.trim()) { setErrors({ email: "Enter your email first" }); return; }
    setSubmitting(true);
    try {
      await requestPasswordlessOtp({ email: form.email.trim() });
      setOtpStage("login");
      setVerificationCode("");
      toast.info("Check your email", { description: "If an active account exists, a six-digit sign-in code has been issued." });
    } catch (error) {
      setErrors({ form: getApiErrorMessage(error, "Email OTP could not be issued.") });
    } finally {
      setSubmitting(false);
    }
  };

  const continuePendingVerification = () => {
    if (!form.email.trim()) { setErrors({ email: "Enter the signup email first" }); return; }
    setErrors({});
    setOtpStage("signup");
    setVerificationCode("");
  };

  const resendOtp = async () => {
    setSubmitting(true);
    try {
      if (otpStage === "signup") await resendRegistrationVerification({ email: form.email.trim() });
      else await requestPasswordlessOtp({ email: form.email.trim() });
      setResendCooldown(60);
      toast.info("Check your email", { description: "If eligible, a new code has been issued." });
    } catch (error) {
      setErrors({ form: getApiErrorMessage(error, "A new code could not be issued yet.") });
    } finally {
      setSubmitting(false);
    }
  };

  const toggleMode = () => { setMode((current) => current === "login" ? "signup" : "login"); setErrors({}); setOtpStage(null); setVerificationCode(""); };
  const title = otpStage === "signup" ? "Verify your email address." : otpStage === "login" ? "Enter your sign-in code." : mode === "login" ? "Login to your account" : "Create your investigator account.";
  const subtitle = otpStage ? "Use the six-digit code from your email. Verification is required before any protected workspace or API is available." : mode === "login" ? "Use your verified account to continue with DRISHYAM." : "Every new account starts as an Investigator. Elevated roles are assigned only by backend policy.";

  return <main className="login-page min-h-screen bg-[#27231e] text-[#241f1a]"><div className="grid min-h-screen lg:grid-cols-[1.12fr_.88fr]">
    <section className="login-scene relative isolate min-h-[510px] overflow-hidden border-b border-white/10 bg-[#2b251f] px-6 py-7 text-[#f6eadb] lg:min-h-screen lg:border-b-0 lg:px-12 lg:py-10">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_48%_24%,rgba(211,160,99,.35),transparent_25%),linear-gradient(125deg,rgba(16,14,12,.82),rgba(44,35,28,.40)_48%,rgba(17,15,13,.88))]"/><div className="login-light absolute left-[49%] top-0 h-40 w-40 -translate-x-1/2 rounded-full bg-[#f6c978]/35 blur-3xl"/><div className="login-dust absolute inset-0 pointer-events-none"><i/><i/><i/><i/><i/><i/></div>
      <img src={SCENE.board} alt="Connected evidence board" className="login-board absolute left-[90%] top-[17%] z-0 w-[55%] -translate-x-1/2 opacity-90 mix-blend-screen lg:top-[16%]"/><img src={SCENE.investigator} alt="Investigator reviewing the evidence board" className="login-investigator pointer-events-none absolute bottom-0 left-[82%] z-[1] h-[58%] -translate-x-1/2 object-contain opacity-95 mix-blend-multiply lg:h-[63%]"/>
      <div className="relative z-10 flex max-w-md flex-col"><button onClick={() => setLocation("/")} className="inline-flex w-fit items-center gap-3 text-left"><img src="/assets/drishyam-eye-mark-new_20260825.png" alt="DRISHYAM mark" className="h-14 w-24 shrink-0 object-contain"/><span className="leading-none"><span className="block text-[19px] font-extrabold tracking-[0.19em] text-[#fff8eb]">DRISHYAM</span><span className="mt-1 block text-[8px] font-bold tracking-[0.19em] text-[#ead5b1]">SEE THE TRUTH. PROVE THE TRUTH.</span></span></button><div className="login-copy mt-20 max-w-[280px] lg:mt-28"><p className="display-serif text-[30px] leading-[1.12] text-[#fff8eb] lg:text-[34px]">Resume the traceable case workspace.</p><p className="mt-4 text-[11px] leading-5 text-[#e5d8c8]">Every source, timestamp, and review decision remains attached to the investigation record.</p><div className="login-feature-stack mt-8 space-y-5">{perks.map(([Icon, label, detail]) => <div key={label} className="flex items-start gap-4"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-[#c49575]/35 bg-[#251b18]/45 text-[#d9a089]"><Icon size={17}/></span><span><span className="block text-[11px] font-extrabold text-[#f1cfbc]">{label}</span><span className="mt-1 block max-w-[195px] text-[11px] leading-5 text-[#e4d4c7]">{detail}</span></span></div>)}</div></div></div><div className="absolute bottom-7 left-1/2 z-10 hidden -translate-x-1/2 rounded border border-[#d3a470]/25 bg-[#171512]/40 px-4 py-2 font-mono text-[9px] font-bold tracking-[.15em] text-[#d9b783] lg:block">TRUTH HAS A TRAIL</div>
    </section>
    <section className="relative grid bg-[#e9dfd2] px-5 py-10 sm:px-8 lg:place-items-center lg:px-12"><div className="absolute inset-0 bg-[radial-gradient(circle_at_82%_8%,rgba(164,74,61,.08),transparent_20%),linear-gradient(115deg,#eee5d9,#e7dccd)]"/><div className="login-access-sheet relative w-full max-w-[520px] rounded-[28px] border border-[#dacbb9] bg-[#fff8ee]/95 p-7 shadow-[0_32px_90px_rgba(49,32,20,.18)] sm:p-11"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-full border border-[#d6bfa8] bg-[#f7ede2] text-[#7f1d1d]"><ShieldCheck size={18}/></span><p className="mono text-[10px] font-bold tracking-[.15em] text-[#7f1d1d]">VERIFIED CASE ACCESS</p></div><h1 className="display-serif mt-8 text-[42px] leading-[.98] tracking-[-.035em] text-[#2e2721]">{title}</h1><p className="mt-4 max-w-md text-sm leading-6 text-[#6f655a]">{subtitle}</p><div className="access-audit-strip mt-6 flex items-center justify-between gap-3 border-y border-[#e5d6c5] py-2.5"><span>IDENTITY / VERIFIED</span><span>SESSION / IN MEMORY</span></div>
      <form onSubmit={submit} className="login-auth-form mt-6 space-y-4">{errors.form && <p className="rounded border border-[#e7b9b1] bg-[#fff0ed] px-3 py-2 text-[10px] font-bold text-[#9c2c25]">{errors.form}</p>}{otpStage ? <label className="block"><span className="sr-only">Verification code</span><div className={`login-input ${errors.otp ? "login-input-error" : ""}`}><MailCheck size={19}/><input value={verificationCode} onChange={(event) => setVerificationCode(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="6-digit verification code"/></div>{errors.otp && <p className="mt-1 text-[10px] font-bold text-[#9c2c25]">{errors.otp}</p>}</label> : <>{mode === "signup" && <label className="block"><span className="sr-only">Full name</span><div className={`login-input ${errors.name ? "login-input-error" : ""}`}><UserRound size={19}/><input value={form.name} onChange={(event) => update("name", event.target.value)} placeholder="Full name" autoComplete="name"/></div>{errors.name && <p className="mt-1 text-[10px] font-bold text-[#9c2c25]">{errors.name}</p>}</label>}<label className="block"><span className="sr-only">Email</span><div className={`login-input ${errors.email ? "login-input-error" : ""}`}><UserRound size={19}/><input value={form.email} onChange={(event) => update("email", event.target.value)} placeholder="Email address" autoComplete="email"/></div>{errors.email && <p className="mt-1 text-[10px] font-bold text-[#9c2c25]">{errors.email}</p>}</label><label className="block"><span className="sr-only">Password</span><div className={`login-input ${errors.password ? "login-input-error" : ""}`}><Lock size={19}/><input value={form.password} onChange={(event) => update("password", event.target.value)} type={passwordVisible ? "text" : "password"} placeholder="Password" autoComplete={mode === "login" ? "current-password" : "new-password"}/><button type="button" onClick={() => setPasswordVisible((value) => !value)} aria-label={passwordVisible ? "Hide password" : "Show password"}>{passwordVisible ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div>{errors.password && <p className="mt-1 text-[10px] font-bold text-[#9c2c25]">{errors.password}</p>}</label>{mode === "signup" && <label className="block"><span className="sr-only">Confirm password</span><div className={`login-input ${errors.confirm ? "login-input-error" : ""}`}><Lock size={19}/><input value={form.confirm} onChange={(event) => update("confirm", event.target.value)} type="password" placeholder="Confirm password" autoComplete="new-password"/></div>{errors.confirm && <p className="mt-1 text-[10px] font-bold text-[#9c2c25]">{errors.confirm}</p>}</label>}</>}<button disabled={submitting} type="submit" className="mt-3 flex w-full items-center justify-center gap-3 rounded-lg bg-[#8c2020] px-5 py-4 text-sm font-extrabold text-white shadow-[0_12px_24px_rgba(127,29,29,.22)] transition hover:bg-[#761a1a] active:scale-[.98] disabled:cursor-wait disabled:opacity-70">{submitting ? "Securing access…" : otpStage ? "Verify and continue" : mode === "login" ? "Login with password" : "Create account"}<ArrowRight size={18}/></button></form>
      {otpStage ? <button disabled={submitting || resendCooldown > 0} type="button" onClick={resendOtp} className="mt-4 w-full text-center text-[10px] font-bold text-[#7f1d1d] underline underline-offset-2 disabled:cursor-not-allowed disabled:opacity-50">{resendCooldown > 0 ? `Resend available in ${resendCooldown}s` : "Resend code"}</button> : mode === "login" && <><div className="my-7 flex items-center gap-4 text-[9px] font-bold text-[#8b8176]"><span className="h-px flex-1 bg-[#ddcfbf]"/>OR<span className="h-px flex-1 bg-[#ddcfbf]"/></div><button disabled={submitting} type="button" onClick={requestOtp} className="flex w-full items-center justify-center gap-3 rounded-lg border border-[#d8c4b0] bg-[#fffaf3] px-5 py-3.5 text-xs font-extrabold text-[#463c33] transition hover:bg-white"><Smartphone size={17} className="text-[#7f1d1d]"/>Login with email OTP</button><button disabled={submitting} type="button" onClick={continuePendingVerification} className="mt-3 flex w-full items-center justify-center gap-2 text-[10px] font-bold text-[#7f1d1d] underline underline-offset-2 disabled:opacity-60"><MailCheck size={14}/>Already received a signup code? Verify email</button>{googleClientId ? <div className="google-login-host mt-3 w-full" ref={googleButton}/> : <p className="mt-4 text-center text-[9px] leading-4 text-[#81756a]">Google sign-in appears only after the verified Google OAuth client is configured locally.</p>}</>}{!otpStage && <p className="mt-7 text-center text-[11px] text-[#6d6359]">{mode === "login" ? "New here?" : "Already have an account?"} <button type="button" onClick={toggleMode} className="font-extrabold text-[#7f1d1d] underline underline-offset-2">{mode === "login" ? "Create an account" : "Login"}</button></p>}<div className="mt-7 flex items-center gap-2 border-t border-[#e4d5c5] pt-5 text-[9px] text-[#81756a]"><Check size={14} className="text-[#7f1d1d]"/>Email verification and server-issued sessions protect access. This device stays signed in until you sign out or access expires.</div>
    </div></section>
  </div></main>;
}
