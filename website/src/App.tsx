import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Features from './pages/Features'
import Technology from './pages/Technology'
import Tools from './pages/Tools'
import Skills from './pages/Skills'
import Docs from './pages/Docs'
import Help from './pages/Help'
import Roadmap from './pages/Roadmap'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/features" element={<Features />} />
        <Route path="/technology" element={<Technology />} />
        <Route path="/tools" element={<Tools />} />
        <Route path="/skills" element={<Skills />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="/help" element={<Help />} />
        <Route path="/roadmap" element={<Roadmap />} />
      </Routes>
    </Layout>
  )
}
