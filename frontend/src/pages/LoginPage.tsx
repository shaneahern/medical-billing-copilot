import { useNavigate, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { LoginForm } from '../components/auth/LoginForm';
import { useAuth } from '../contexts/AuthContext';

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated } = useAuth();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/chat';

  useEffect(() => {
    if (isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, from]);

  const handleLoginSuccess = () => {
    navigate(from, { replace: true });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900">Medical Billing Copilot</h1>
          <p className="mt-2 text-sm text-gray-600">
            Sign in to access your billing assistant
          </p>
        </div>

        <div className="bg-white py-8 px-6 shadow-lg rounded-xl">
          <LoginForm onSuccess={handleLoginSuccess} />
        </div>

        <p className="text-center text-xs text-gray-500">
          Secure access for authorized billing staff only
        </p>
      </div>
    </div>
  );
}
