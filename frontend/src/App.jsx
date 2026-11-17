import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout, RequireAuth } from './components/Layout'
import { useAuth } from './context/AuthContext'
import Landing from './pages/Landing'
import { LoginPage, RegisterPage } from './pages/Auth'
import Dashboard from './pages/Dashboard'
import Courses from './pages/Courses'
import CourseDetail from './pages/CourseDetail'
import TopicPage from './pages/TopicPage'
import QuizPage from './pages/QuizPage'
import ResultPage from './pages/ResultPage'
import MockTests from './pages/MockTests'
import ExamPage from './pages/ExamPage'
import ExamResult from './pages/ExamResult'
import HistoryPage from './pages/HistoryPage'
import ProfilePage from './pages/ProfilePage'
import NotFound from './pages/NotFound'
import AdminHome from './pages/admin/AdminHome'
import AdminCourses from './pages/admin/AdminCourses'
import ManageCourse from './pages/admin/ManageCourse'
import ManageTopic from './pages/admin/ManageTopic'
import AdminUsers from './pages/admin/AdminUsers'
import AdminSettings from './pages/admin/AdminSettings'

function Home() {
  const { user, loading } = useAuth()
  if (loading) return null
  return user ? <Navigate to="/dashboard" replace /> : <Landing />
}

const admin = (el) => <RequireAuth admin>{el}</RequireAuth>

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* The exam hall is full-screen (no sidebar) to mirror real exam conditions. */}
      <Route path="/exam/:examId" element={<RequireAuth><ExamPage /></RequireAuth>} />

      <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="courses" element={<Courses />} />
        <Route path="courses/:courseId" element={<CourseDetail />} />
        <Route path="topics/:topicId" element={<TopicPage />} />
        <Route path="topics/:topicId/quiz" element={<QuizPage />} />
        <Route path="attempts/:attemptId" element={<ResultPage />} />
        <Route path="mock-tests" element={<MockTests />} />
        <Route path="exam/:examId/result" element={<ExamResult />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="profile" element={<ProfilePage />} />

        <Route path="admin" element={admin(<AdminHome />)} />
        <Route path="admin/courses" element={admin(<AdminCourses />)} />
        <Route path="admin/courses/:courseId" element={admin(<ManageCourse />)} />
        <Route path="admin/topics/:topicId" element={admin(<ManageTopic />)} />
        <Route path="admin/users" element={admin(<AdminUsers />)} />
        <Route path="admin/settings" element={admin(<AdminSettings />)} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
