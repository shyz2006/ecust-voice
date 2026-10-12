const assert=require('assert'),path=require('path');
module.exports=async function checkCopyPolish(page,out){
  await page.evaluate(()=>switchTab('campus'));
  const details=page.locator('.campus-evidence');
  await details.waitFor({state:'visible'});
  const results=[];
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===1440?1000:844});
    await details.evaluate(el=>el.open=false);
    await details.locator('summary .evidence-sample').click();
    assert(await details.evaluate(el=>el.open));
    const styles=await details.evaluate(el=>({
      background:getComputedStyle(el).backgroundColor,
      cards:[...el.querySelectorAll('.kpi-card')].map(card=>getComputedStyle(card).backgroundColor),
      banner:getComputedStyle(el.querySelector('.crisis-alert-banner')).backgroundColor,
      text:el.textContent,
      overflow:document.documentElement.scrollWidth>window.innerWidth+1
    }));
    assert.notEqual(styles.background,'rgb(255, 255, 255)');
    assert(styles.cards.every(color=>color!=='rgb(255, 255, 255)'));
    assert.notEqual(styles.banner,'rgb(255, 255, 255)');
    assert(!styles.text.includes('保证分析语料纯净真实'));
    assert(!styles.text.includes('非全校随机样本'));
    assert(styles.text.includes('采集覆盖等级'));
    assert.equal(styles.overflow,false,'Page should fit mobile viewport');
    await details.screenshot({path:path.join(out,`copy-polish-${width}.png`)});
    await details.locator('summary .evidence-sample').click();assert(!(await details.evaluate(el=>el.open)));
    results.push({width,background:styles.background,banner:styles.banner,horizontalOverflow:styles.overflow});
  }
  return results;
};
