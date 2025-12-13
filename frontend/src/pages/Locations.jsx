import React, { useEffect, useState } from 'react'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Typography from '@mui/material/Typography'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import { useNavigate } from 'react-router-dom'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export default function Locations({ onSelectLocation }){
  const [locations, setLocations] = useState([])
  const navigate = useNavigate()

  useEffect(()=>{
    fetchLocations()
  },[])

  async function fetchLocations(){
    try{
      const resp = await fetch(API + '/locations')
      const data = await resp.json()
      setLocations(data.locations || [])
    }catch(err){
      console.error('fetchLocations', err)
    }
  }

  function select(loc){
    if(onSelectLocation) onSelectLocation(loc)
    navigate('/')
  }

  return (
    <div>
      <Typography variant="h5" sx={{ mb: 2, fontWeight: 700, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Locations</Typography>
      <List>
        {locations.map((loc, index)=> (
          <ListItem key={loc} disablePadding>
            <ListItemButton 
              onClick={()=>select(loc)}
              sx={{
                '&:hover': {
                  background: 'rgba(102,126,234,0.08)',
                  transform: 'translateX(8px)',
                },
                transition: 'all 0.3s ease',
              }}
            >
              <ListItemText 
                primary={loc}
                primaryTypographyProps={{
                  sx: {
                    color: '#667eea',
                    fontWeight: 500,
                  },
                }}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
        <Button 
          variant="outlined" 
          onClick={()=>{ if(onSelectLocation) onSelectLocation(null); navigate('/') }}
          sx={{
            borderColor: '#667eea',
            color: '#764ba2',
            '&:hover': {
              borderColor: '#764ba2',
              background: 'rgba(102,126,234,0.08)',
            },
          }}
        >
          Clear Filter
        </Button>
      </Stack>
    </div>
  )
}
