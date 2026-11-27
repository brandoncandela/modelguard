import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import AppShell from "./components/layout/AppShell";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import ExecutiveOverview from "./pages/ExecutiveOverview";
import ModelInventory from "./pages/ModelInventory";
import PerformanceMonitoring from "./pages/PerformanceMonitoring";
import ValidationManagement from "./pages/ValidationManagement";
import FindingsRemediation from "./pages/FindingsRemediation";
import AIGovernance from "./pages/AIGovernance";
import RegulatoryControls from "./pages/RegulatoryControls";
import CommitteeReporting from "./pages/CommitteeReporting";
import AuditTrail from "./pages/AuditTrail";

function Guard({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Spinner label="Restoring session" />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Guard><AppShell /></Guard>}>
        <Route index element={<ExecutiveOverview />} />
        <Route path="inventory" element={<ModelInventory />} />
        <Route path="inventory/:modelId" element={<ModelInventory />} />
        <Route path="monitoring" element={<PerformanceMonitoring />} />
        <Route path="monitoring/:modelId" element={<PerformanceMonitoring />} />
        <Route path="validations" element={<ValidationManagement />} />
        <Route path="validations/:validationId" element={<ValidationManagement />} />
        <Route path="findings" element={<FindingsRemediation />} />
        <Route path="findings/:findingId" element={<FindingsRemediation />} />
        <Route path="ai" element={<AIGovernance />} />
        <Route path="ai/:systemId" element={<AIGovernance />} />
        <Route path="regulatory" element={<RegulatoryControls />} />
        <Route path="reporting" element={<CommitteeReporting />} />
        <Route path="audit" element={<AuditTrail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
