import React from 'react'
import AppBar from '@mui/material/AppBar'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import Button from '@mui/material/Button'
import Box from '@mui/material/Box'
import { Link as RouterLink } from 'react-router-dom'
import Link from '@mui/material/Link'
import { motion } from 'framer-motion'

export default function NavBar(){
  return (
    <AppBar 
      position="static"
      sx={{
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        boxShadow: '0 4px 20px rgba(102, 126, 234, 0.3)',
      }}
    >
      <Toolbar>
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Typography 
            variant="h6" 
            sx={{ 
              flexGrow: 1, 
              fontWeight: 700,
              fontSize: '1.5rem',
              letterSpacing: '0.5px',
            }}
          >
            Property Hub
          </Typography>
        </motion.div>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Link component={RouterLink} to="/" color="inherit" underline="none">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Button 
                color="inherit"
                sx={{
                  '&:hover': {
                    background: 'rgba(255, 255, 255, 0.15)',
                  },
                  transition: 'all 0.3s ease',
                }}
              >
                Listings
              </Button>
            </motion.div>
          </Link>
          <Link component={RouterLink} to="/locations" color="inherit" underline="none">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Button 
                color="inherit"
                sx={{
                  '&:hover': {
                    background: 'rgba(255, 255, 255, 0.15)',
                  },
                  transition: 'all 0.3s ease',
                }}
              >
                Locations
              </Button>
            </motion.div>
          </Link>
          <Link component={RouterLink} to="/add-listing" color="inherit" underline="none">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Button 
                color="inherit"
                sx={{
                  '&:hover': {
                    background: 'rgba(255, 255, 255, 0.15)',
                  },
                  transition: 'all 0.3s ease',
                }}
              >
                Add Listing
              </Button>
            </motion.div>
          </Link>
          <Link component={RouterLink} to="/edit-delete-listing" color="inherit" underline="none">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Button 
                color="inherit"
                sx={{
                  '&:hover': {
                    background: 'rgba(255, 255, 255, 0.15)',
                  },
                  transition: 'all 0.3s ease',
                }}
              >
                Edit/Delete Listing
              </Button>
            </motion.div>
          </Link>
          <Link component={RouterLink} to="/compare" color="inherit" underline="none">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Button 
                color="inherit"
                sx={{
                  '&:hover': {
                    background: 'rgba(255, 255, 255, 0.15)',
                  },
                  transition: 'all 0.3s ease',
                }}
              >
                Compare
              </Button>
            </motion.div>
          </Link>
          <Link component={RouterLink} to="/chatbot" color="inherit" underline="none">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Button 
                color="inherit"
                sx={{
                  '&:hover': {
                    background: 'rgba(255, 255, 255, 0.15)',
                  },
                  transition: 'all 0.3s ease',
                }}
              >
                Chatbot
              </Button>
            </motion.div>
          </Link>
        </Box>
      </Toolbar>
    </AppBar>
  )
}
