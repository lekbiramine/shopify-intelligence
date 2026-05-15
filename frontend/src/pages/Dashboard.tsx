import { useSearchParams } from 'react-router-dom'

export default function Dashboard() {
  const [searchParams] = useSearchParams()
  const shop = searchParams.get('shop')

  return (
    <div style={{
      minHeight: '100vh',
      background: '#08080F',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexDirection: 'column',
      gap: '16px'
    }}>
      <div style={{color:'#5C6BFF', fontSize:'40px'}}>◆</div>
      <h1 style={{
        color: '#FFFFFF',
        fontSize: '24px',
        fontWeight: 700,
        margin: 0
      }}>
        PERSPICOR
      </h1>
      <p style={{color:'#8888AA', fontSize:'14px', margin:0}}>
        {shop ? `Connected: ${shop}` : 'Dashboard coming soon'}
      </p>
      <p style={{
        color:'#555570', 
        fontSize:'13px', 
        margin:0,
        textAlign:'center',
        maxWidth:'400px'
      }}>
        Your daily report is being sent to your inbox every morning.
        Full dashboard coming soon.
      </p>
    </div>
  )
}
