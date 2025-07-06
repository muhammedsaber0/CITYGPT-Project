import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './ChatBox.css';

function ChatBox() {
  const [messages, setMessages] = useState([{ sender: 'bot', text: '📝 Please describe the traffic scenario you want to simulate:' }]);
  const [input, setInput] = useState('');
  const [step, setStep] = useState('ask-scenario');
  const [scenarioPath, setScenarioPath] = useState('');
  const [roads, setRoads] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const sendMessage = async () => {
    if (!input.trim() && step !== 'ask-blocked') return;

    const newMessages = [...messages, { sender: 'user', text: input }];
    setMessages(newMessages);
    setInput('');
    setIsLoading(true);

    try {
      if (step === 'ask-scenario') {
        const res = await axios.post('http://localhost:8080/generate-scenario', { user_input: input });
        if (res.data.success) {
          const roads = res.data.roads || [];
          setRoads(roads);

          const roadList = roads.map(r => {
            const lanes = r.lanes.map(l => `${l.lt} (${l.dir}, ${(l.width / 1000).toFixed(1)} m)`).join('; ');
            return `ID: ${r.id}\nName: ${r.name}\nLanes: ${lanes || 'None'}\n`;
          }).join('\n');

          const roadIdsWithNames = roads.map(r => `${r.id} (${r.name})`).join(', ');
          const combinedMessage = `✅ Scenario generated. Roads involved:\n\n${roadList}\n🛑 You can block any of these Road IDs: ${roadIdsWithNames}\nEnter road IDs to block (comma-separated), or type -1 to skip blocking:`;

          setMessages([...newMessages, { sender: 'bot', text: combinedMessage }]);
          setScenarioPath(res.data.scenario_bin_path);
          setStep('ask-blocked');
        } else {
          setMessages([...newMessages, { sender: 'bot', text: `❌ ${res.data.message}\nPlease enter a new scenario:` }]);
        }
      } else if (step === 'ask-blocked') {
        const blockedIds = input.trim() === '-1'
          ? []
          : input.split(',').map(id => parseInt(id.trim())).filter(id => !isNaN(id));

        const res = await axios.post('http://localhost:8080/simulate-with-blocked-roads', {
          blocked_road_ids: blockedIds,
          scenario_bin_path: scenarioPath,
          user_input: messages.find(msg => msg.sender === 'user')?.text || ''
        });
        if (res.data.success) {
          const m = res.data.metrics;
          setMessages([...newMessages, { sender: 'bot', text: `📊 Simulation complete!\nAvg Time: ${m.avg_travel_time_hms}, Max Delay: ${m.max_delay_hms}, Trips: ${m.num_trips}\n\n📝 You can now enter another scenario:` }]);
          setStep('ask-scenario');
        } else {
          setMessages([...newMessages, { sender: 'bot', text: `❌ ${res.data.message}\nPlease re-enter road IDs to block or type -1 to skip:` }]);
        }
      }
    } catch (error) {
      console.error('Error:', error);
      setMessages([...newMessages, { sender: 'bot', text: '⚠️ Error occurred. Please try again.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') sendMessage();
  };

  const resetConversation = () => {
    setMessages([{ sender: 'bot', text: '📝 Please describe the traffic scenario you want to simulate:' }]);
    setInput('');
    setStep('ask-scenario');
    setScenarioPath('');
    setRoads([]);
    setIsLoading(false);
  };

  return (
    <div className="chat-container">
      <div className="chat-header">🏙️ CityGPT</div>
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble ${msg.sender}`}>
            {msg.text.split('\n').map((line, idx) => (
              <div key={idx}>{line}</div>
            ))}
          </div>
        ))}
        {isLoading && <div className="chat-bubble bot">⏳ Processing...</div>}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-area" style={{ display: 'flex', gap: '10px' }}>
        <input
          type="text"
          placeholder={step === 'ask-scenario' ? "Describe your scenario..." : "Enter road IDs to block or type -1 to skip"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          disabled={isLoading}
        />
        <div style={{ display: 'flex', gap: '10px' }}>
          <button onClick={sendMessage} disabled={isLoading}>Send</button>
          <button onClick={resetConversation} style={{ backgroundColor: '#f44336', color: 'white' }}>Reset</button>
        </div>
      </div>
    </div>
  );
}

export default ChatBox;