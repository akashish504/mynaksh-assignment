// Decide which pages a visitor may see.

import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { Loading } from "./Loading";

// Login and signup: only for visitors who are not logged in.
export function PublicOnly() {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  if (me) return <Navigate to="/chat" replace />;
  return <Outlet />;
}

// Onboarding: logged in, profile not complete yet.
export function NeedsOnboarding() {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  if (!me) return <Navigate to="/login" replace />;
  if (me.profile_complete) return <Navigate to="/chat" replace />;
  return <Outlet />;
}

// The app itself: logged in AND onboarded. Onboarding is forced before chat.
export function RequireProfile() {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  if (!me) return <Navigate to="/login" replace />;
  if (!me.profile_complete) return <Navigate to="/onboarding" replace />;
  return <Outlet />;
}
