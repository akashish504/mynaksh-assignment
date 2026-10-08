import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { NeedsOnboarding, PublicOnly, RequireProfile } from "./components/RouteGuards";
import { AuthPage } from "./pages/AuthPage";
import { ChatPage } from "./pages/ChatPage";
import { MemoryPage } from "./pages/MemoryPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { ProfilePage } from "./pages/ProfilePage";

export default function App() {
  return (
    <Routes>
      <Route element={<PublicOnly />}>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />
      </Route>

      <Route element={<NeedsOnboarding />}>
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>

      <Route element={<RequireProfile />}>
        <Route element={<AppLayout />}>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
