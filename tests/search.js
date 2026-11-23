// Browser test: searching a monument or victim by name and picking the
// first hit opens its popup. Run by tests/run.html. (Place search calls
// Nominatim, so it is not tested here.)
window.__tests.push({name:'search', run:async function(){
  var wait = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
  var fails = [];

  async function pick(query, expect){
    var q = document.getElementById('q');
    q.value = query;
    q.dispatchEvent(new Event('input'));
    var first = document.querySelector('#hits button');
    if(!first){ return 'no hits for "' + query + '"'; }
    first.click();
    await wait(400);
    var p = document.querySelector('.leaflet-popup-content');
    var text = p ? p.textContent : '';
    if(p){ document.querySelector('.leaflet-popup-close-button').click(); }
    return text.indexOf(expect) >= 0 ? '' : 'picking "' + query + '" did not open its popup';
  }

  // A dated monument and a named victim, taken from the data itself.
  var m = MON.find(function(d){ return d[2] && d[3] === 'M' && d[5].length > 12; });
  var v = LYN.find(function(d){ return d[5] && d[5] !== 'Unknown' && d[5].split(' ').length > 1; });

  var r1 = await pick(m[5], m[5]);
  if(r1){ fails.push(r1); }
  var r2 = await pick(v[5], v[5]);
  if(r2){ fails.push(r2); }
  return fails;
}});
